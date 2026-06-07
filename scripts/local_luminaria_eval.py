"""Local deterministic eval for the luminaria dynamic prompt gate.

This intentionally does not instantiate Agent and does not call Gateway,
Reasoning Engine, Vertex, MCP, Postgres, BigQuery, or GitHub Actions. It checks
the local code path that decides whether the heavy `reparo_luminaria`
interactive prompt is injected into a turn.

Run:
  uv run python scripts/local_luminaria_eval.py
  uv run python scripts/local_luminaria_eval.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from engine.luminaria_prompt_gate import (
    INTERACTIVE_RESPONSE_PROMPT,
    _inject_interactive_response_prompt,
    _should_inject_interactive_response_prompt,
)
from engine.luminaria_interactive_prompt import interactive_response_dynamic_enabled
from engine.session_boundary import CLOSE_DIRECTIVE
from src.prompt_modules import compose, interactive_response


_FORBIDDEN_REMOTE_MODULE_PREFIXES = (
    "engine.agent",
    "engine.mcp_tools",
    "google.cloud.aiplatform",
    "langchain_google_vertexai",
    "langgraph.checkpoint.postgres",
    "psycopg",
    "src.deploy",
    "src.interactive_test",
    "src.utils.cleanup_reasoning_engines",
    "src.utils.gateway_chat",
    "vertexai",
)


@dataclass(frozen=True)
class GateCase:
    id: str
    messages: list[Any]
    expected: bool
    reason: str


@dataclass(frozen=True)
class CheckResult:
    id: str
    passed: bool
    expected: Any
    actual: Any
    reason: str


def _module_matches_prefix(module_name: str, prefix: str) -> bool:
    return module_name == prefix or module_name.startswith(f"{prefix}.")


def _loaded_forbidden_remote_modules() -> list[str]:
    return sorted(
        module_name
        for module_name in sys.modules
        if any(
            _module_matches_prefix(module_name, prefix)
            for prefix in _FORBIDDEN_REMOTE_MODULE_PREFIXES
        )
    )


def _flow_submission_text() -> str:
    return (
        "[SYSTEM] O cidadao preencheu o formulario WhatsApp. Dados recebidos: "
        '{"defect_type":"Apagada","qty_pattern":"uma","location":"Rua"}. '
        "ACAO OBRIGATORIA: Chame a ferramenta multi_step_service imediatamente "
        "com service_name='reparo_luminaria' e payload contendo os dados recebidos "
        "(adicione _source='whatsapp_flow')."
    )


def _accented_flow_submission_text() -> str:
    return (
        "[SYSTEM] O cidadão preencheu o formulário WhatsApp. Dados recebidos: "
        '{"defect_type":"Apagada","qty_pattern":"uma","location":"Rua"}. '
        "AÇÃO OBRIGATÓRIA: Chame a ferramenta multi_step_service imediatamente "
        "com service_name='reparo_luminaria' e payload contendo os dados recebidos "
        "(adicione _source='whatsapp_flow')."
    )


def _gate_cases() -> list[GateCase]:
    positives = [
        ("explicit_luminaria", "A luminaria da minha rua esta apagada"),
        ("rioluz_wire_hazard", "Tem fio caido com faisca perto do poste da Rioluz"),
        ("public_lighting", "A iluminacao publica falhou na minha rua"),
        ("public_light_square", "A luz da praca apagou"),
        ("plural_luminarias", "Tem duas luminarias apagadas"),
        ("plural_accented_luminarias", "Tem duas luminárias apagadas"),
        ("plural_street_lamps", "As lampadas da rua queimaram"),
        ("plural_accented_post_lamps", "As lâmpadas do poste queimaram"),
        ("plural_street_lights", "As luzes da rua apagaram"),
        ("plural_square_lights", "As luzes da praca apagaram"),
        ("plural_post_lights", "As luzes dos postes apagaram"),
        ("plural_avenue_lights", "As luzes da avenida estao piscando"),
        ("rio_luz_spaced", "Como falar com Rio Luz?"),
        ("rio_luz_hyphenated", "Quero atendimento da Rio-Luz"),
        ("dark_square", "A praca esta escura"),
        ("dark_avenue", "A avenida esta escura"),
        ("dark_logradouro", "O logradouro esta escuro"),
        ("alameda_no_lighting", "A alameda esta sem iluminacao"),
        ("dark_roundabout", "A rotatoria esta escura"),
        ("dark_alley", "O beco ta escuro"),
        ("dark_park", "O parque esta escuro"),
        ("dark_court", "A quadra ficou escura"),
        ("sidewalk_no_lighting", "A calcada esta sem iluminacao"),
        ("dark_tunnel", "O tunel esta escuro"),
        ("dark_accented_tunnel", "O túnel está escuro"),
        ("tunnel_lights", "As luzes do tunel apagaram"),
        ("accented_tunnel_lights", "As luzes do túnel apagaram"),
        ("dark_viaduct", "O viaduto esta escuro"),
        ("walkway_no_lighting", "A passarela esta sem iluminacao"),
        ("bike_lane_lights", "As luzes da ciclovia apagaram"),
        ("dark_public_stairs", "A escadaria esta escura"),
        ("waterfront_no_lighting", "A orla esta sem iluminacao"),
        ("named_street_dark", "A Rua das Flores esta escura"),
        ("named_avenue_dark", "A Avenida Brasil ficou no escuro"),
        ("named_square_very_dark", "A Praca Sao Salvador esta muito escura"),
        ("named_brt_walkway_dark", "A passarela do BRT esta escura"),
        ("bus_stop_dark", "O ponto de onibus esta escuro"),
        ("accented_bus_stop_no_lighting", "O ponto de ônibus está sem iluminação"),
        ("brt_station_no_lighting", "A estacao de BRT esta sem iluminacao"),
        ("square_has_no_lighting", "A praca nao tem iluminacao"),
        ("post_power_outage", "Falta luz no poste da Rua A"),
        ("plural_named_streets_dark", "As ruas do bairro estao escuras"),
        ("plural_accented_streets_dark", "As ruas do bairro estão escuras"),
        ("plural_streets_no_lighting", "Varias ruas estao sem iluminacao"),
        ("plural_squares_dark", "As praças estão escuras"),
        ("plural_avenues_dark", "As avenidas ficaram no escuro"),
        ("whole_block_dark", "O quarteirao inteiro esta escuro"),
        ("plural_blocks_no_lighting", "Os quarteiroes estao sem iluminacao"),
        ("plural_walkways_dark", "As passarelas estão às escuras"),
        ("plural_bike_lanes_no_light", "As ciclovias estão sem luz"),
        ("plural_alleys_dark", "Os becos estão escuros"),
        ("interleaved_street_lights", "As luzes da rua estao uma sim uma nao"),
        ("alternating_avenue_fixtures", "As luminarias da avenida estao alternadas"),
        ("half_square_lamps_off", "Metade das lampadas da praca apagou"),
        ("street_segment_no_light", "Um trecho da rua esta sem luz"),
        ("whole_court_no_lighting", "A quadra inteira esta sem iluminacao"),
        ("many_street_lamps_burned", "Varias lampadas da rua queimaram"),
        ("single_post_lamp_off", "So uma lampada do poste apagou"),
        ("corner_lamp_burned", "A lampada da esquina queimou"),
        ("accented_corner_lamp_off", "A lâmpada da esquina está apagada"),
        ("corner_light_off", "A luz da esquina apagou"),
        ("dark_corner", "A esquina está escura"),
        ("lamp_in_front_of_number", "A lampada em frente ao numero 50 queimou"),
        ("light_in_front_of_store", "A luz em frente ao mercado apagou"),
        ("light_in_front_of_church", "A luz em frente a igreja apagou"),
        ("light_in_front_of_church_da", "A luz em frente da igreja apagou"),
        ("lamp_in_front_of_pharmacy", "A lampada em frente a farmacia queimou"),
        ("light_in_front_of_restaurant", "A luz em frente ao restaurante apagou"),
        ("light_in_front_of_daycare", "A luz em frente a creche esta apagada"),
        ("light_in_front_of_upa", "A luz em frente a UPA apagou"),
        ("light_near_home", "A luz perto da minha casa apagou"),
        ("lamp_near_bar", "A lampada perto do bar esta queimada"),
        ("lamp_near_bakery", "A lampada perto da padaria esta queimada"),
        ("light_near_church", "A luz perto da igreja fica piscando"),
        ("public_fixture_in_front_store", "A luminaria publica em frente a loja apagou"),
        ("sidewalk_light_in_front_restaurant", "A luz da calcada em frente ao restaurante apagou"),
        ("street_post_in_front_market", "O poste da rua em frente ao mercado esta piscando"),
        ("public_light_building_facade", "A luz publica na fachada do predio apagou"),
        ("public_light_in_front_condo", "A luz publica em frente ao condominio apagou"),
        ("public_luminaria_in_front_building", "A luminaria publica em frente ao predio apagou"),
        ("street_post_in_front_condo", "O poste da rua em frente ao condominio esta apagado"),
        ("sidewalk_light_building", "A luz da calcada do predio apagou"),
        ("post_arm_broken", "O braco do poste quebrou"),
        ("accented_post_arm_broken", "O braço do poste está quebrado"),
        ("public_reflector_broken", "O refletor da praca quebrou"),
        ("post_arm_unstable", "O braco do poste esta bambo"),
        ("post_support_almost_falling", "O suporte do poste esta prestes a cair"),
        ("street_luminaria_unstable", "A haste da luminaria da rua esta instavel"),
        ("corner_luminaria_almost_falling", "A luminaria da esquina esta quase caindo"),
        ("street_photocell_burned", "A fotocelula da rua queimou"),
        ("accented_street_photocell_burned", "A fotocélula da rua queimou"),
        ("square_relay_burned", "O rele da praca queimou"),
        ("accented_post_relay_defect", "O relé do poste está com defeito"),
        ("avenue_reactor_defective", "O reator da avenida esta defeituoso"),
        ("post_socket_broken", "O soquete do poste quebrou"),
        ("post_not_lighting", "O poste nao acende"),
        ("post_light_not_lighting", "A luz do poste nao acende"),
        ("post_lamp_not_turning_on", "A lampada do poste nao liga"),
        ("public_light_not_working", "A luz publica nao esta funcionando"),
        ("replace_street_lamp", "Precisa trocar a lampada da rua"),
        ("replace_square_fixture", "Tem que substituir a luminaria da praca"),
        ("replace_post_light", "Quero pedir troca da luz do poste"),
        ("restore_post_lamp", "Precisa repor a lampada do poste"),
        ("replace_post_reactor", "Tem que trocar o reator do poste"),
        ("replace_street_photocell", "Precisa substituir a fotocelula da rua"),
        ("replace_square_relay", "Quero trocar o rele da praca"),
        ("replace_street_fixture_stronger", "Trocar a luminaria da rua por luz mais forte"),
        ("street_light_weak", "A luz da rua esta fraca"),
        ("post_lamp_weak", "A lampada do poste esta fraca"),
        ("post_weak_light", "O poste esta com luz fraca"),
        ("fixture_weak", "A luminaria esta fraca"),
        ("street_poorly_lit", "A rua esta mal iluminada"),
        ("square_poorly_lit", "A praca esta mal iluminada"),
        ("public_lighting_weak", "A iluminacao da rua esta fraca"),
        ("post_light_on_day", "A luz do poste fica acesa de dia"),
        ("fixture_on_day", "A luminaria fica acesa durante o dia"),
        ("post_on_day", "O poste fica aceso de dia"),
        ("post_toggles", "O poste apaga e acende toda hora"),
        ("street_lamp_toggles", "A lampada da rua fica apagando e acendendo"),
        ("post_light_oscillating", "A luz do poste esta oscilando"),
        ("street_lamp_burst", "A lampada da rua estourou"),
        ("square_fixture_burst", "A luminaria da praca estourou"),
        ("post_lamp_exploded", "A lampada do poste explodiu"),
        ("post_light_failed", "A luz do poste pifou"),
        ("street_light_turning_off_often", "A luz da rua fica apagando direto"),
        ("corner_lamp_turning_off_often", "A lampada da esquina vive apagando"),
        ("fixture_half_light", "A luminaria esta em meia luz"),
        ("square_light_half_phase", "A luz da praca esta em meia fase"),
        ("corner_lamp_intermitent", "A lampada da esquina fica intermitente"),
        ("street_fixture_noise", "A luminaria da rua esta fazendo barulho"),
        ("post_fixture_noise", "A luminaria do poste esta com ruido"),
        ("post_buzzing", "O poste esta fazendo zumbido"),
        ("square_lamp_hissing", "A lampada da praca esta chiando"),
        ("post_light_clicking", "A luz do poste faz estalo"),
        ("fixture_reactor_noise", "O reator da luminaria esta roncando"),
        ("post_photocell_noise", "A fotocelula do poste esta fazendo barulho"),
        ("lamp_on_post", "A lampada do poste queimou"),
        ("fallen_post", "O poste caiu com fios expostos"),
        ("shock_wire", "Tem cabo caido na rua dando choque"),
        ("public_wire_hanging", "Tem fio pendurado no poste da rua"),
        ("public_cable_low", "Tem cabo baixo na rua perto do poste"),
        ("public_wire_bare", "Fio desencapado na iluminacao publica"),
        ("post_wiring_exposed", "A fiacao do poste esta exposta"),
        ("post_energized", "O poste esta energizado"),
        ("post_short", "O poste esta dando curto"),
        ("post_short_circuit", "Tem curto-circuito no poste da praca"),
        ("street_wood_post_fell", "O poste de madeira da rua caiu"),
        ("energized_post_shock", "O poste esta com energia dando choque"),
        ("energy_wire_shock", "Tem fio de energia dando choque na rua"),
        ("light_energy_wire_shock", "Tem fio de energia da Light dando choque na rua"),
        ("public_lighting_cable", "O cabo da iluminacao publica caiu na rua"),
        ("rioluz_cable", "O cabo da Rioluz arrebentou no poste"),
        ("rioluz_wire_loose", "Fio da Rioluz esta solto na calcada"),
        ("street_fixture_wire_sparking", "O fio da luminaria da rua esta faiscando"),
        ("public_lighting_wires_stolen", "Roubaram os fios da iluminacao publica"),
        ("street_fixture_cable_stolen", "Furtaram o cabo da luminaria da rua"),
        ("post_wiring_taken", "Levaram a fiacao do poste"),
        ("rioluz_wires_cut", "Cortaram os fios da Rioluz"),
        ("street_post_vandalized", "O poste da rua foi vandalizado"),
        ("square_fixture_damaged_by_vandalism", "A luminaria da praca foi depredada"),
        ("sidewalk_fixture_intentionally_broken", "Quebraram a luminaria da calcada de proposito"),
        ("street_dark", "A rua esta escura faz dois dias"),
        ("street_lighting", "A iluminacao da minha rua apagou"),
        ("repair_request", "Quero abrir reparo de luz publica na Rua A, 10"),
        ("unknown_rioluz_but_street_fixture_off", "Nao sei se e Rioluz, mas a luminaria da rua apagou"),
        ("not_just_info_open_repair", "Nao quero so informar, quero abrir reparo de luminaria"),
        ("more_posts_street", "Quero pedir mais postes na minha rua"),
        ("street_needs_more_posts", "A rua precisa de mais postes"),
        ("square_new_fixture", "A praca precisa de luminaria nova"),
        ("install_public_fixture", "Quero instalar luminaria publica na rua"),
        ("street_without_lighting_posts", "A rua esta sem postes de iluminacao"),
        ("reinstall_light_point_sidewalk", "Precisa reinstalar ponto de luz na calcada"),
        ("removed_street_light_post", "Tiraram o poste de luz da rua e nao recolocaram"),
        ("alley_needs_light_point", "A viela precisa de ponto de luz"),
    ]
    negatives = [
        ("tree_pruning", "Como faco para solicitar poda de arvore?"),
        ("tree_near_post", "Preciso podar uma arvore encostando no poste da rua"),
        ("internet_cable_home", "Meu cabo de internet arrebentou dentro de casa"),
        ("internet_cable_street", "Meu cabo de internet caiu na rua"),
        ("bedroom_lamp", "A lampada do quarto queimou"),
        ("living_room_light", "A iluminacao da sala esta ruim"),
        ("home_lights", "As luzes da casa apagaram"),
        ("living_room_lights", "As luzes da sala estao piscando"),
        ("bedroom_lights", "As luzes do quarto queimaram"),
        ("living_room_light_weak", "A luz da sala esta fraca"),
        ("bedroom_lamp_weak", "A lampada do quarto esta fraca"),
        ("kitchen_poorly_lit", "A cozinha esta mal iluminada"),
        ("living_room_poorly_lit", "A sala esta mal iluminada"),
        ("tv_on_day", "A TV fica acesa de dia"),
        ("porch_light_on_day", "A luz da varanda fica acesa de dia"),
        ("tv_toggles", "A TV apaga e acende toda hora"),
        ("living_room_lamp_toggles", "A lampada da sala fica apagando e acendendo"),
        ("bedroom_light_oscillating", "A luz do quarto esta oscilando"),
        ("living_room_lamp_burst", "A lampada da sala estourou"),
        ("store_fixture_burst", "A luminaria da loja estourou"),
        ("kitchen_lamp_exploded", "A lampada da cozinha explodiu"),
        ("tv_failed", "A TV pifou"),
        ("bedroom_light_turning_off_often", "A luz do quarto fica apagando direto"),
        ("office_lamp_turning_off_often", "A lampada do escritorio vive apagando"),
        ("garage_luminaria_half_light", "A luminaria da garagem esta em meia luz"),
        ("cellphone_screen_blinking", "A tela do celular fica piscando de madrugada"),
        ("living_room_fixture_noise", "A luminaria da sala esta fazendo barulho"),
        ("bedroom_lamp_noise", "A lampada do quarto esta com ruido"),
        ("fridge_buzzing", "A geladeira esta fazendo zumbido"),
        ("tv_hissing", "A TV esta chiando"),
        ("porch_light_clicking", "A luz da varanda faz estalo"),
        ("living_room_reactor_noise", "O reator da sala esta roncando"),
        ("dark_bedroom", "Meu quarto esta escuro"),
        ("dark_living_room", "A sala ta escura"),
        ("dark_home_stairs", "A escada da minha casa esta escura"),
        ("garage_no_lighting", "A garagem esta sem iluminacao"),
        ("negated_named_street_dark", "A Rua das Flores nao esta escura"),
        ("negated_logradouro_dark", "O logradouro nao esta escuro"),
        ("condo_alameda_dark", "A alameda do condominio esta escura"),
        ("garage_roundabout_dark", "A rotatoria da garagem esta escura"),
        ("subway_station_no_lighting", "A estacao de metro esta sem iluminacao"),
        ("internet_point_no_light", "O ponto de internet esta sem luz"),
        ("bus_interior_no_light", "O onibus esta sem luz"),
        ("negated_square_no_lighting", "A praca nao esta sem iluminacao"),
        ("light_power_outage", "Falta luz na rua toda por causa da Light"),
        ("light_post_fallen", "O poste da Light caiu na rua"),
        ("light_energy_wire", "Tem fio de energia da Light caido na rua"),
        ("electric_grid_down", "A rede eletrica da rua caiu"),
        ("plural_classrooms_dark", "As salas de aula estao escuras"),
        ("plural_garages_no_lighting", "As garagens estao sem iluminacao"),
        ("plural_building_stairs_dark", "As escadas do predio estao escuras"),
        ("plural_streets_negated_dark", "As ruas nao estao escuras"),
        ("plural_squares_negated_no_lighting", "As praças não estão sem iluminação"),
        ("block_negated_dark", "O quarteirao nao esta escuro"),
        ("square_negated_poorly_lit", "A praca nao esta mal iluminada"),
        ("plural_streets_negated_poorly_lit", "As ruas nao estao mal iluminadas"),
        ("living_room_interleaved_lights", "As luzes da sala estao uma sim uma nao"),
        ("building_alternating_luminarias", "As luminarias do predio estao alternadas"),
        ("store_half_lamps_off", "Metade das lampadas da loja apagou"),
        ("garage_segment_no_light", "Um trecho da garagem esta sem luz"),
        ("tv_block_no_signal", "A quadra da TV esta sem sinal"),
        ("kitchen_lamp_burned", "A lampada da cozinha queimou"),
        ("porch_light_off", "A luz da varanda apagou"),
        ("mirror_lamp_burned", "A lampada em frente ao espelho queimou"),
        ("bed_light_off", "A luz perto da cama apagou"),
        ("corner_negated_dark", "A esquina nao esta escura"),
        ("condo_post_light", "A luz do poste do condominio queimou"),
        ("condo_post_lamp", "A lâmpada do poste do condomínio apagou"),
        ("garage_post", "O poste da garagem esta piscando"),
        ("private_parking_post", "O poste do estacionamento privado caiu"),
        ("building_luminaria", "A luminaria da portaria do predio apagou"),
        ("home_garden_luminaria", "A luminaria do jardim de casa queimou"),
        ("yard_post", "O poste do quintal caiu"),
        ("fence_post_fell", "O poste da cerca caiu"),
        ("clothesline_post_broken", "O poste do varal quebrou"),
        ("antenna_post_bent", "O poste da antena entortou"),
        ("sign_post_fell", "O poste da placa caiu"),
        ("fence_mesh_post_loose", "O poste do alambrado esta solto"),
        ("volleyball_net_post_fell", "O poste da rede de volei caiu"),
        ("farm_wood_post_fell", "O poste de madeira do sitio caiu"),
        ("store_luminaria", "A luminaria da loja apagou"),
        ("market_lamp", "A lampada do mercado queimou"),
        ("bar_light_blinking", "A luz do bar esta piscando"),
        ("pharmacy_luminaria", "A luminaria da farmacia esta piscando"),
        ("church_lamp", "A lampada da igreja queimou"),
        ("bakery_light", "A luz da padaria esta fraca"),
        ("daycare_lamp", "A lampada da creche apagou"),
        ("upa_luminaria", "A luminaria da UPA esta com problema"),
        ("building_luminaria_direct", "A luminaria do predio apagou"),
        ("office_lamp", "A lampada do escritorio queimou"),
        ("restaurant_luminaria_noise", "A luminaria do restaurante esta fazendo barulho"),
        ("store_facade_light", "A luz da fachada da loja apagou"),
        ("market_parking_reflector", "O refletor do estacionamento do mercado queimou"),
        ("chair_arm_broken", "O braco da cadeira quebrou"),
        ("tv_support_broken", "O suporte da TV quebrou"),
        ("living_room_globe_broken", "O globo da sala quebrou"),
        ("water_tank_lid_fallen", "A tampa da caixa d agua caiu"),
        ("yard_reflector_burned", "O refletor do quintal queimou"),
        ("gate_stem_bent", "A haste do portao entortou"),
        ("tv_support_unstable", "O suporte da TV esta bambo"),
        ("gate_stem_unstable", "A haste do portao esta instavel"),
        ("antenna_almost_falling", "A antena esta quase caindo"),
        ("garage_photocell_burned", "A fotocelula da garagem queimou"),
        ("gate_relay_burned", "O rele do portao queimou"),
        ("kitchen_socket_broken", "O soquete da cozinha quebrou"),
        ("living_room_reactor_defective", "O reator da sala esta defeituoso"),
        ("tv_not_turning_on", "A TV nao liga"),
        ("room_lamp_not_lighting", "A lampada da sala nao acende"),
        ("kitchen_light_not_working", "A luz da cozinha nao funciona"),
        ("building_corridor_light_not_lighting", "A luz do corredor do predio nao acende"),
        ("replace_living_room_lamp", "Precisa trocar a lampada da sala"),
        ("replace_store_fixture", "Tem que substituir a luminaria da loja"),
        ("replace_bedroom_light", "Quero trocar a luz do quarto"),
        ("restore_office_lamp", "Precisa repor a lampada do escritorio"),
        ("replace_living_room_reactor", "Tem que trocar o reator da sala"),
        ("replace_garage_photocell", "Precisa substituir a fotocelula da garagem"),
        ("home_power_outage", "A luz acabou na minha casa"),
        ("traffic_light", "O semaforo apagou no cruzamento"),
        ("traffic_light_square", "O semaforo da praca apagou"),
        ("phone_wire", "O fio do telefone caiu na calcada"),
        ("tv_cable", "A tv a cabo parou e o cabo esta solto"),
        ("kite_wire_on_post", "Tem fio de pipa preso no poste da rua"),
        ("clothesline_wire_on_post", "Tem fio de varal preso no poste da rua"),
        ("barbed_wire_on_post", "Tem arame farpado preso no poste da rua"),
        ("banner_wire_on_post", "Tem fio de faixa preso no poste"),
        ("telecom_post", "O poste de telefonia caiu na rua"),
        ("provider_wire", "O fio da Claro caiu na calcada"),
        ("fiber_wire", "Tem fio de fibra caido na rua"),
        ("fiber_wire_on_post", "Tem fio de fibra caido no poste"),
        ("provider_cable_post", "O cabo da Vivo no poste arrebentou"),
        ("internet_cable_exposed_post", "O cabo de internet esta exposto no poste"),
        ("provider_wire_exposed", "O fio da Claro esta exposto na calcada"),
        ("home_outlet_short", "A tomada da sala esta dando curto"),
        ("building_energy_panel_energized", "O quadro de energia do predio esta energizado"),
        ("not_public_light_home_lamp", "Nao e luz publica, e a lampada da minha casa"),
        ("not_public_fixture_store_light", "Nao e luminaria publica, e a luz da loja"),
        ("does_not_want_luminaria_repair", "Nao quero reparo de luminaria, quero poda de arvore"),
        ("street_does_not_need_lighting", "A rua nao precisa de iluminacao"),
        ("square_does_not_need_more_posts", "A praca nao precisa de mais postes"),
        ("cellphone_stolen_street", "Roubaram meu celular na rua"),
        ("internet_cable_stolen", "Furtaram o cabo da internet"),
        ("home_wiring_taken", "Levaram a fiacao da minha casa"),
        ("provider_wires_cut", "Cortaram os fios da Claro"),
        ("gate_vandalized", "O portao foi vandalizado"),
        ("living_room_fixture_intentionally_broken", "A luminaria da sala foi quebrada de proposito"),
        ("more_energy_posts_light", "Quero pedir mais postes de energia para a Light"),
        ("internet_post_terrain", "Preciso de poste para internet no meu terreno"),
        ("install_yard_fixture", "Quero instalar luminaria no quintal"),
        ("garage_new_fixture", "A garagem precisa de luminaria nova"),
        ("reinstall_living_room_lamp", "Precisa reinstalar a lampada da sala"),
        ("removed_private_gate_post", "Tiraram o poste do meu portao"),
        ("internet_rio_luz", "Minha internet da Rio Luz caiu"),
        ("fiber_rio_luz", "A fibra da Rio-Luz caiu"),
    ]

    cases = [
        GateCase(
            id=case_id,
            messages=[HumanMessage(content=text)],
            expected=True,
            reason="turno atual e de reparo/risco de iluminacao publica",
        )
        for case_id, text in positives
    ]
    cases.extend(
        GateCase(
            id=case_id,
            messages=[HumanMessage(content=text)],
            expected=False,
            reason="servico ou contexto nao deve receber prompt de luminaria",
        )
        for case_id, text in negatives
    )
    cases.extend(
        [
            GateCase(
                id="latest_turn_wins_negative",
                messages=[
                    HumanMessage(content="A luminaria da rua esta apagada"),
                    AIMessage(content="[Flow de luminaria]"),
                    HumanMessage(content="Agora quero solicitar poda de arvore"),
                ],
                expected=False,
                reason="historico antigo de luminaria nao contamina outro servico",
            ),
            GateCase(
                id="latest_turn_wins_positive",
                messages=[
                    HumanMessage(content="Como faco para solicitar poda?"),
                    AIMessage(content="Posso orientar."),
                    HumanMessage(content="Tambem tem uma luminaria apagada na rua"),
                ],
                expected=True,
                reason="turno atual de luminaria deve ativar o prompt dinamico",
            ),
            GateCase(
                id="multipart_text",
                messages=[
                    HumanMessage(
                        content=[
                            {"type": "text", "text": "A luminaria da rua apagou"},
                            {
                                "type": "image_url",
                                "image_url": {"url": "https://example/img"},
                            },
                        ]
                    )
                ],
                expected=True,
                reason="conteudo multimodal com texto relevante deve ativar gate",
            ),
            GateCase(
                id="flow_submission_unaccented",
                messages=[
                    HumanMessage(content="A luminaria da rua esta apagada"),
                    AIMessage(content="[Flow de luminaria]"),
                    HumanMessage(content=_flow_submission_text()),
                ],
                expected=False,
                reason="submissao de WhatsApp Flow ja e tratada por outro modulo",
            ),
            GateCase(
                id="flow_submission_accented",
                messages=[
                    HumanMessage(content="A luminaria da rua esta apagada"),
                    AIMessage(content="[Flow de luminaria]"),
                    HumanMessage(content=_accented_flow_submission_text()),
                ],
                expected=False,
                reason="submissao real do Mule com acentos nao deve reabrir Flow",
            ),
        ]
    )
    return cases


def _evaluate_gate() -> list[CheckResult]:
    results = []
    for case in _gate_cases():
        actual = _should_inject_interactive_response_prompt(case.messages)
        results.append(
            CheckResult(
                id=f"gate::{case.id}",
                passed=actual == case.expected,
                expected=case.expected,
                actual=actual,
                reason=case.reason,
            )
        )
    return results


def _evaluate_prompt_contract() -> list[CheckResult]:
    augmented_prompt, version = compose("BASE", "v0")
    checks = [
        (
            "dynamic_enabled",
            True,
            interactive_response_dynamic_enabled(),
            "kill-switch local deve deixar prompt dinamico ativo",
        ),
        (
            "not_global_prompt",
            False,
            interactive_response.MODULE_PROMPT in augmented_prompt,
            "prompt pesado nao deve entrar no system prompt global",
        ),
        (
            "not_global_version",
            False,
            "interactive_response" in version,
            "versao global nao deve carregar sufixo interactive_response",
        ),
        (
            "service_scope",
            True,
            "reparo_luminaria" in INTERACTIVE_RESPONSE_PROMPT,
            "prompt dinamico deve continuar escopado ao servico certo",
        ),
        (
            "wire_defect_mapping",
            True,
            'defect_type="Danificada"' in INTERACTIVE_RESPONSE_PROMPT,
            "furto/cabo/fios deve mapear para defeito canonico do Flow",
        ),
        (
            "noise_defect_mapping",
            True,
            'defect_type="Com ruído"' in INTERACTIVE_RESPONSE_PROMPT,
            "barulho/ruido deve mapear para defeito canonico do Flow",
        ),
        (
            "physical_defect_mapping",
            True,
            (
                'defect_type="Danificada"' in INTERACTIVE_RESPONSE_PROMPT
                and 'defect_type="Pendurada"' in INTERACTIVE_RESPONSE_PROMPT
                and "bambo" in INTERACTIVE_RESPONSE_PROMPT
                and "quase caindo" in INTERACTIVE_RESPONSE_PROMPT
            ),
            "componentes fisicos instaveis devem mapear defeito canonico do Flow",
        ),
        (
            "out_of_scope_route",
            True,
            "Fora de escopo" in INTERACTIVE_RESPONSE_PROMPT,
            "prompt deve preservar rota de fora de escopo antes do Flow",
        ),
    ]
    return [
        CheckResult(
            id=f"contract::{check_id}",
            passed=actual == expected,
            expected=expected,
            actual=actual,
            reason=reason,
        )
        for check_id, expected, actual, reason in checks
    ]


def _evaluate_injection() -> list[CheckResult]:
    close = SystemMessage(content=CLOSE_DIRECTIVE)
    messages = [
        SystemMessage(content="memoria"),
        HumanMessage(content="A luminaria apagou, era so isso"),
        close,
    ]
    injected = _inject_interactive_response_prompt(messages)
    order = [type(message).__name__ for message in injected]

    already_injected = [
        SystemMessage(content="memoria"),
        SystemMessage(content=INTERACTIVE_RESPONSE_PROMPT),
        HumanMessage(content="A luminaria apagou"),
    ]
    idempotent = _inject_interactive_response_prompt(already_injected)

    checks = [
        (
            "order",
            ["SystemMessage", "SystemMessage", "HumanMessage", "SystemMessage"],
            order,
            "prompt dinamico entra apos sistemas iniciais e antes da conversa",
        ),
        (
            "content_position",
            True,
            injected[1].content == INTERACTIVE_RESPONSE_PROMPT,
            "prompt injetado deve ser exatamente o modulo de luminaria",
        ),
        (
            "trailing_directive_precedence",
            True,
            injected[-1] is close,
            "diretiva transitoria final deve manter maior precedencia",
        ),
        (
            "idempotent",
            True,
            idempotent is already_injected,
            "nao deve duplicar prompt se ele ja estiver presente",
        ),
    ]
    return [
        CheckResult(
            id=f"injection::{check_id}",
            passed=actual == expected,
            expected=expected,
            actual=actual,
            reason=reason,
        )
        for check_id, expected, actual, reason in checks
    ]


def _evaluate_locality_contract() -> list[CheckResult]:
    loaded_forbidden_modules = _loaded_forbidden_remote_modules()
    return [
        CheckResult(
            id="locality::no_remote_modules_loaded",
            passed=loaded_forbidden_modules == [],
            expected=[],
            actual=loaded_forbidden_modules,
            reason=(
                "eval local nao deve carregar Agent, Gateway, Vertex, MCP "
                "ou Postgres"
            ),
        )
    ]


def run_eval() -> dict[str, Any]:
    checks = [
        *_evaluate_gate(),
        *_evaluate_prompt_contract(),
        *_evaluate_injection(),
        *_evaluate_locality_contract(),
    ]
    failures = [check for check in checks if not check.passed]
    groups: dict[str, dict[str, Any]] = {}
    for check in checks:
        group = check.id.split("::", 1)[0]
        current = groups.setdefault(group, {"total": 0, "passed": 0})
        current["total"] += 1
        current["passed"] += int(check.passed)
    for data in groups.values():
        data["score"] = data["passed"] / data["total"] if data["total"] else 0.0

    loaded_forbidden_modules = _loaded_forbidden_remote_modules()
    return {
        "name": "local_luminaria_eval",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "offline": True,
        "calls_gateway": any(
            _module_matches_prefix(module_name, "src.utils.gateway_chat")
            for module_name in loaded_forbidden_modules
        ),
        "calls_reasoning_engine": any(
            _module_matches_prefix(module_name, prefix)
            for module_name in loaded_forbidden_modules
            for prefix in (
                "engine.agent",
                "src.deploy",
                "src.interactive_test",
                "src.utils.cleanup_reasoning_engines",
            )
        ),
        "calls_vertex": any(
            _module_matches_prefix(module_name, prefix)
            for module_name in loaded_forbidden_modules
            for prefix in (
                "google.cloud.aiplatform",
                "langchain_google_vertexai",
                "vertexai",
            )
        ),
        "calls_mcp": any(
            _module_matches_prefix(module_name, "engine.mcp_tools")
            for module_name in loaded_forbidden_modules
        ),
        "loaded_forbidden_modules": loaded_forbidden_modules,
        "dynamic_enabled": interactive_response_dynamic_enabled(),
        "summary": {
            "total": len(checks),
            "passed": len(checks) - len(failures),
            "failed": len(failures),
            "score": (len(checks) - len(failures)) / len(checks),
            "groups": groups,
        },
        "checks": [check.__dict__ for check in checks],
    }


def _print_human(result: dict[str, Any]) -> None:
    summary = result["summary"]
    print("local_luminaria_eval")
    print(f"  offline: {result['offline']}")
    print(f"  gateway: {result['calls_gateway']}")
    print(f"  reasoning_engine: {result['calls_reasoning_engine']}")
    print(f"  vertex: {result['calls_vertex']}")
    print(f"  mcp: {result['calls_mcp']}")
    print(
        "  score: "
        f"{summary['passed']}/{summary['total']} "
        f"({summary['score']:.2%})"
    )
    for group, data in summary["groups"].items():
        print(
            f"  {group}: {data['passed']}/{data['total']} "
            f"({data['score']:.2%})"
        )
    failures = [check for check in result["checks"] if not check["passed"]]
    if not failures:
        print("PASS")
        return
    print("FAIL")
    for failure in failures:
        print(
            f"  - {failure['id']}: expected={failure['expected']!r} "
            f"actual={failure['actual']!r} ({failure['reason']})"
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local deterministic luminaria eval."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of the human summary.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the JSON result.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = run_eval()
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n")
    if args.json:
        print(payload)
    else:
        _print_human(result)
    return 0 if result["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
