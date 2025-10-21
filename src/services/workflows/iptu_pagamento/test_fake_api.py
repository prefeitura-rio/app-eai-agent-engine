"""
Testes para demonstrar o uso da API fake com diferentes cenários.
"""

import asyncio
from src.services.workflows.iptu_pagamento.api_service_fake import IPTUAPIServiceFake


async def test_scenarios():
    """
    Testa diferentes cenários com a API fake.
    """
    api = IPTUAPIServiceFake()
    
    print("=== TESTE DA API FAKE - CENÁRIOS MOCKADOS ===\n")
    
    # Cenário 1: Inscrição com IPTU + Taxa de Lixo
    print("1. CENÁRIO: Inscrição 01234567890123 (IPTU + Taxa de Lixo)")
    guias = await api.consultar_guias("01234567890123", 2024)
    if guias:
        print(f"   ✅ Encontradas {guias.total_guias} guias:")
        for guia in guias.guias:
            print(f"      - Guia {guia.numero_guia}: R$ {guia.valor_numerico:.2f}")
    else:
        print("   ❌ Nenhuma guia encontrada")
    print()
    
    # Cenário 2: Apenas IPTU
    print("2. CENÁRIO: Inscrição 11111111111111 (Apenas IPTU)")
    guias = await api.consultar_guias("11111111111111", 2024)
    if guias:
        print(f"   ✅ Encontradas {guias.total_guias} guias:")
        for guia in guias.guias:
            print(f"      - Guia {guia.numero_guia}: R$ {guia.valor_numerico:.2f}")
    else:
        print("   ❌ Nenhuma guia encontrada")
    print()
    
    # Cenário 3: Inscrição não encontrada
    print("3. CENÁRIO: Inscrição 99999999999999 (Não encontrada)")
    guias = await api.consultar_guias("99999999999999", 2024)
    if guias:
        print(f"   ✅ Encontradas {guias.total_guias} guias")
    else:
        print("   ❌ Nenhuma guia encontrada (como esperado)")
    print()
    
    # Cenário 4: Ano inválido
    print("4. CENÁRIO: Ano 2019 (Fora do range)")
    guias = await api.consultar_guias("01234567890123", 2019)
    if guias:
        print(f"   ✅ Encontradas {guias.total_guias} guias")
    else:
        print("   ❌ Nenhuma guia encontrada (como esperado)")
    print()
    
    # Cenário 5: Teste de cotas para IPTU
    print("5. CENÁRIO: Cotas do IPTU (Guia 00)")
    cotas = await api.obter_cotas("01234567890123", 2024, "00")
    if cotas:
        print(f"   ✅ Encontradas {cotas.total_cotas} cotas, valor total: R$ {cotas.valor_total:.2f}")
        # Mostra algumas cotas de exemplo
        for i, cota in enumerate(cotas.cotas[:5]):
            status = "PAGA" if cota.esta_paga else "VENCIDA" if cota.esta_vencida else "EM ABERTO"
            print(f"      - Cota {cota.numero_cota}: R$ {cota.valor_numerico:.2f} ({status})")
        if len(cotas.cotas) > 5:
            print(f"      ... e mais {len(cotas.cotas) - 5} cotas")
    else:
        print("   ❌ Nenhuma cota encontrada")
    print()
    
    # Cenário 6: Teste de DARM para cotas específicas
    print("6. CENÁRIO: DARM para cotas 04,05,06 do IPTU")
    darm = await api.consultar_darm("01234567890123", 2024, "00", ["04", "05", "06"])
    if darm and darm.darm:
        print(f"   ✅ DARM gerado: R$ {darm.darm.valor_numerico:.2f}")
        print(f"      Linha digitável: {darm.darm.sequencia_numerica}")
        print(f"      Código de barras: {darm.darm.codigo_barras}")
        print(f"      Cotas: {', '.join([c.ncota for c in darm.darm.cotas])}")
    else:
        print("   ❌ DARM não gerado")
    print()
    
    # Cenário 7: Teste de PDF
    print("7. CENÁRIO: Download PDF do DARM")
    pdf_base64 = await api.download_pdf_darm("01234567890123", 2024, "00", ["04", "05", "06"])
    if pdf_base64:
        print(f"   ✅ PDF gerado com {len(pdf_base64)} caracteres")
        print(f"      Primeiros 50 chars: {pdf_base64[:50]}...")
    else:
        print("   ❌ PDF não gerado")
    print()
    
    print("=== RESUMO DOS CENÁRIOS DE TESTE ===")
    print("✅ Inscrições com dados:")
    print("   - 01234567890123: IPTU + Taxa de Lixo (valores padrão)")
    print("   - 11111111111111: Apenas IPTU")
    print("   - 22222222222222: Apenas Taxa de Lixo")
    print("   - 33333333333333: Todas as guias quitadas (filtradas)")
    print("   - 44444444444444: IPTU com valor alto (teste desconto)")
    print("   - 55555555555555: IPTU com valor baixo")
    print()
    print("❌ Cenários de erro:")
    print("   - Qualquer outra inscrição: Não encontrada")
    print("   - Anos fora do range 2020-2025: Não encontrados")
    print("   - Guias inexistentes: Retorna None")
    print("   - Cotas inexistentes: Retorna None")


if __name__ == "__main__":
    asyncio.run(test_scenarios())