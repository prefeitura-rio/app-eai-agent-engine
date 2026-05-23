"""Unit tests for MeterProvider bootstrap helpers in Agent.

Cobre o `_build_metric_exporter`: cada strategy (`otlp`, `console`, `none`,
unknown) + cenário endpoint vazio. Não chama `_set_up_opentelemetry` direto
(esse setup acopla TracerProvider + LangchainInstrumentor que pedem mais
dependências); valida apenas a branch que decide o exporter.
"""

from __future__ import annotations

from unittest.mock import patch

from opentelemetry.sdk.metrics.export import ConsoleMetricExporter

from engine.agent import Agent


# OTel env vars que tests precisam isolar do ambiente do CI/dev shell —
# sem isso, valores preconfigurados na máquina (e.g. setados por dotenv
# global) sobreescrevem assumptions de "env não-setada" no test, gerando
# flake. `_mock_getenv` returna unset (default) pra essas keys, exceto
# quando o test explicitamente override.
_OTEL_ENV_KEYS_TO_ISOLATE = frozenset({
    "OTEL_METRICS_EXPORTER",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_HEADERS",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
    "OTEL_METRIC_EXPORT_INTERVAL_MILLIS",
})


def _build_bare_agent(**env_overrides) -> Agent:
    """Cria Agent sem rodar `set_up()` — só populamos campos suficientes
    pra `_build_metric_exporter` ler.

    Patch ``os.getenv`` antes da construção pra que `__init__` capture as
    env vars desejadas. Keys OTel são ISOLADAS do ambiente real (retorna
    default) exceto se explicitamente override — protege contra flake por
    env preconfigurada no CI/dev shell.
    """
    real_getenv = __import__("os").getenv

    def _mock_getenv(key, default=None):
        if key in env_overrides:
            return env_overrides[key]
        if key in _OTEL_ENV_KEYS_TO_ISOLATE:
            # Forçar fallback ao default — protege contra env real do shell.
            return default
        return real_getenv(key, default)

    with patch("engine.agent.getenv", side_effect=_mock_getenv):
        # Apenas args mínimos; tools=[] não dispara setup pesado em __init__.
        agent = Agent(tools=[])
    return agent


def test_build_metric_exporter_console_strategy():
    """`OTEL_METRICS_EXPORTER=console` retorna ConsoleMetricExporter
    independente de endpoint setado (stdout não precisa).
    """
    agent = _build_bare_agent(
        OTEL_METRICS_EXPORTER="console",
        OTEL_EXPORTER_OTLP_METRICS_ENDPOINT="",
    )
    exporter = agent._build_metric_exporter()
    assert isinstance(exporter, ConsoleMetricExporter)


def test_build_metric_exporter_none_strategy_returns_none():
    """`OTEL_METRICS_EXPORTER=none` skip MeterProvider (returns None)."""
    agent = _build_bare_agent(OTEL_METRICS_EXPORTER="none")
    assert agent._build_metric_exporter() is None


def test_build_metric_exporter_empty_strategy_returns_none():
    """Empty string == disabled explícito (operador setou `=""` pra opt-out).
    Não pode ser reescrito pra default `otlp` — disable é intencional.
    """
    # Mesmo com trace endpoint setado, empty strategy desabilita explicit.
    agent = _build_bare_agent(
        OTEL_METRICS_EXPORTER="",
        OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="http://collector:4318/v1/traces",
    )
    assert agent._build_metric_exporter() is None


def test_build_metric_exporter_otlp_without_endpoint_returns_none():
    """OTLP sem endpoint configurado → fail-safe None (não bota MeterProvider
    apontando pra lugar nenhum, deixa noop)."""
    agent = _build_bare_agent(
        OTEL_METRICS_EXPORTER="otlp",
        OTEL_EXPORTER_OTLP_METRICS_ENDPOINT="",
        OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="",
    )
    assert agent._build_metric_exporter() is None


def test_build_metric_exporter_otlp_with_endpoint_returns_exporter():
    """OTLP com endpoint válido constrói o exporter."""
    agent = _build_bare_agent(
        OTEL_METRICS_EXPORTER="otlp",
        OTEL_EXPORTER_OTLP_METRICS_ENDPOINT="http://localhost:4318/v1/metrics",
    )
    exporter = agent._build_metric_exporter()
    assert exporter is not None
    # Verifica que é OTLPMetricExporter (não ConsoleMetricExporter); shape
    # mínimo.
    assert not isinstance(exporter, ConsoleMetricExporter)


def test_build_metric_exporter_falls_back_to_trace_endpoint():
    """Sem `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` (env não setada), usa trace
    endpoint como fallback — single-collector deploys não precisam configurar
    duas envs. Nota: passar `""` (string vazia) é diferente de não setar —
    env vazia retorna `""` real e desativa exporter (fail-safe).
    """
    # Não passa OTEL_EXPORTER_OTLP_METRICS_ENDPOINT no override pra simular
    # env não-setada (getenv default kick in).
    agent = _build_bare_agent(
        OTEL_METRICS_EXPORTER="otlp",
        OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="http://collector:4318/v1/traces",
    )
    exporter = agent._build_metric_exporter()
    assert exporter is not None
    assert not isinstance(exporter, ConsoleMetricExporter)


def test_metrics_endpoint_path_normalized_from_trace_endpoint():
    """Quando trace endpoint termina em `/v1/traces`, metrics endpoint deve
    ser normalizado pra `/v1/metrics` — coletor OTLP usa paths distintos por
    signal type; reaproveitar o trace URL crua → 404 no /v1/traces.
    """
    agent = _build_bare_agent(
        OTEL_METRICS_EXPORTER="otlp",
        OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="http://collector:4318/v1/traces",
    )
    assert agent._otlp_metrics_endpoint == "http://collector:4318/v1/metrics"


def test_metrics_endpoint_unchanged_when_trace_no_v1_traces_suffix():
    """Trace endpoint sem `/v1/traces` (coletor custom path) fica intocado."""
    agent = _build_bare_agent(
        OTEL_METRICS_EXPORTER="otlp",
        OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="http://collector:4318/otlp",
    )
    assert agent._otlp_metrics_endpoint == "http://collector:4318/otlp"


def test_metrics_endpoint_explicit_takes_precedence_over_trace():
    """Quando `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` explícito, ignora trace
    endpoint mesmo que ambos setados — operador soube o que estava fazendo.
    """
    agent = _build_bare_agent(
        OTEL_METRICS_EXPORTER="otlp",
        OTEL_EXPORTER_OTLP_METRICS_ENDPOINT="http://metrics:4318/v1/metrics",
        OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="http://traces:4318/v1/traces",
    )
    assert agent._otlp_metrics_endpoint == "http://metrics:4318/v1/metrics"


def test_build_metric_exporter_with_jwt_padding_in_headers():
    """JWT/Bearer headers tem `=` no base64 padding. `split('=')` sem maxsplit
    quebra com ValueError ('too many values to unpack'). Validar que parsing
    aceita value com '=' embed corretamente — startup não pode falhar por isso.
    """
    agent = _build_bare_agent(
        OTEL_METRICS_EXPORTER="otlp",
        OTEL_EXPORTER_OTLP_METRICS_ENDPOINT="http://collector:4318/v1/metrics",
        # Header com `==` padding (Base64-encoded JWT/Bearer)
        OTEL_EXPORTER_OTLP_METRICS_HEADERS="Authorization=Bearer eyJhbGc==",
    )
    # Deve construir sem crashar:
    exporter = agent._build_metric_exporter()
    assert exporter is not None
    assert not isinstance(exporter, ConsoleMetricExporter)


def test_build_metric_exporter_unknown_strategy_returns_none():
    """Strategy desconhecido → None + warning log (não crash)."""
    agent = _build_bare_agent(OTEL_METRICS_EXPORTER="invalid_strategy_xyz")
    exporter = agent._build_metric_exporter()
    assert exporter is None


def test_meter_provider_default_none_before_setup():
    """`_meter_provider` é None até `_set_up_opentelemetry()` rodar.
    Garante que reads antes do setup não disparam AttributeError."""
    agent = _build_bare_agent(OTEL_METRICS_EXPORTER="none")
    assert agent._meter_provider is None


def test_metric_export_interval_default():
    """Default 60000ms quando env não setada."""
    agent = _build_bare_agent()
    assert agent._otel_metric_export_interval_ms == 60000


def test_metric_export_interval_custom():
    """Custom value via env var."""
    agent = _build_bare_agent(OTEL_METRIC_EXPORT_INTERVAL_MILLIS="10000")
    assert agent._otel_metric_export_interval_ms == 10000


def test_metric_export_interval_invalid_falls_back_to_default():
    """Valor inválido (não-int) cai pra default — não crasha boot."""
    agent = _build_bare_agent(OTEL_METRIC_EXPORT_INTERVAL_MILLIS="not_a_number")
    assert agent._otel_metric_export_interval_ms == 60000


def test_metric_export_interval_zero_clamped_to_default():
    """0ms é syntaxicamente válido mas rejeitado pelo PeriodicExporting
    MetricReader (ValueError no constructor). Clamp pra default evita
    fail-hard no startup por env errada."""
    agent = _build_bare_agent(OTEL_METRIC_EXPORT_INTERVAL_MILLIS="0")
    assert agent._otel_metric_export_interval_ms == 60000


def test_metric_export_interval_negative_clamped_to_default():
    """Negativo também rejeitado pelo reader — clamp pra default."""
    agent = _build_bare_agent(OTEL_METRIC_EXPORT_INTERVAL_MILLIS="-5000")
    assert agent._otel_metric_export_interval_ms == 60000
