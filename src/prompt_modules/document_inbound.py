"""
Módulo de prompt: instruções para o LLM chamar a tool MCP
``analyze_inbound_document`` (Gemini — PDF/TXT/CSV) depois de
``register_inbound_media`` quando o cidadão envia um documento pelo WhatsApp.

Estrutura espelha ``vision_inbound`` / ``video_inbound`` via
``AnalyzableMediaSpec`` (ADR-018). Este arquivo fica só com o que é
document-specific: como usar o conteúdo extraído no atendimento.

A UM anexa o documento como ``ContentVersion`` (validado ao vivo 2026-07-02:
FileType=PDF). O download + leitura acontecem no MCP; aqui só ensinamos o LLM
a chamar a tool e aproveitar o texto extraído sem pedir o cidadão redigitar.
"""

from src.prompt_modules._analyzable_media_template import (
    AnalyzableMediaSpec,
    render_module_prompt,
)

MODULE_NAME = "document_inbound"


_DOCUMENT_GUIDANCE = """\
### Retorno de `analyze_inbound_document`

O `analysis` retornado tem o schema:

```
{
  "conteudo_extraido": "<texto que o Gemini leu do documento: resumo do pedido, endereco, dados relevantes>"
}
```

### Como usar o conteúdo extraído

- Trate `analysis.conteudo_extraido` como **mensagem real do cidadão** — o que
  ele mandou no documento equivale ao que teria digitado. **NÃO** peça pra
  repetir em texto o que já está no arquivo.
- **Continue o atendimento normalmente** com base no conteúdo extraído,
  exatamente como faria se o cidadão tivesse digitado o mesmo texto. As regras
  de serviço, triagem de escopo e workflows são as dos demais módulos deste
  prompt — este módulo só garante que o conteúdo do documento **entre** no
  atendimento; não redefine fluxo de serviço.
- Se a tool retornar `status` diferente de `analyzed` (ex.: `deferred`,
  `rejected`) ou `conteudo_extraido` vazio, use o `suggested_reply_pt_br` como
  base e peça a informação em texto.

### Exemplo de uso

Cidadão anexa um PDF. `analyze_inbound_document` retorna
`analysis.conteudo_extraido = "..."` com o texto lido. Próximo passo do LLM:
usar esse texto como a mensagem do cidadão e seguir o atendimento normal (sem
pedir pra redigitar), confirmando brevemente que leu o documento.
"""


_SPEC = AnalyzableMediaSpec(
    module_name=MODULE_NAME,
    media_type="document",
    analyze_tool="analyze_inbound_document",
    domain_noun_singular="documento",
    domain_noun_indefinite="um documento",
    domain_action="ler",
    domain_action_present="leitura",
    accepted_extensions=("pdf", "txt", "csv", "rtf"),
    rejected_extensions_note=(
        "doc/docx/xls/xlsx/ppt/pptx são binários que o Gemini não lê direto — "
        "caem em fallback 'envie como PDF'."
    ),
    bytes_base64_arg_name="document_bytes_base64",
    local_path_arg_name="local_document_path",
    enable_env_var="ENABLE_DOCUMENT_ADDENDUM",
    skip_analyze_on_real_user_text=False,  # caption não substitui a leitura do arquivo
    type_specific_guidance=_DOCUMENT_GUIDANCE,
)


MODULE_PROMPT = render_module_prompt(_SPEC)
