"""Tradução da interface (português ↔ inglês).

O texto em português é a chave; `T()` devolve a versão do idioma atual e aplica
`str.format` quando há parâmetros. Para incluir um idioma novo, adicione-o em LANGS e
crie um dicionário como EN.
"""
from __future__ import annotations

import os

LANGS = {"pt": "Português", "en": "English"}

EN = {
    # Janela principal
    "Importar IR": "Import IR",
    "Abrir arquivo WAV…": "Open WAV file…",
    "Converter para 48 kHz": "Resample to 48 kHz",
    "Otimizar para 512 amostras (fase mínima)": "Optimise for 512 samples (minimum phase)",
    "Concentra a energia do IR no início, para que o corte em 512 amostras (limite do pedal) "
    "preserve melhor o timbre, sobretudo os graves.":
        "Concentrates the IR's energy at the start so that truncating to 512 samples (the pedal's limit) "
        "preserves the tone better, especially the low end.",
    "Distance: {v}%": "Distance: {v}%",
    "Gravar no slot:": "Write to slot:",
    "Gravar IR no pedal": "Write IR to pedal",
    "Nenhum IR carregado": "No IR loaded",
    "Ferramentas": "Tools",
    "Fazer backup dos IRs…": "Back up IRs…",
    "Restaurar backup de IRs…": "Restore IR backup…",
    "IRs de fábrica": "Factory IRs",
    "Presets de fábrica": "Factory presets",
    "Preset": "Preset",
    "Editar preset:": "Edit preset:",
    "Salvar presets no pedal": "Save presets to pedal",
    "Idioma:": "Language:",
    "Procurando o pedal…": "Looking for the pedal…",
    # Seções
    "IR": "IR",
    "Ambiente": "Ambience",
    "Tonalidade": "Tone",
    "{name}: ligado": "{name}: on",
    "{name}: desligado": "{name}: off",
    # Conexão
    "Conectado: Cube Baby AC (chip 0x{chip:04X}).": "Connected: Cube Baby AC (chip 0x{chip:04X}).",
    "{msg} Tentando de novo…": "{msg} Retrying…",
    "Conexão perdida: {msg}.": "Connection lost: {msg}.",
    "Primeira conexão: fazendo backup dos IRs do pedal…": "First connection: backing up the pedal's IRs…",
    "Backup inicial do pedal salvo em {path}": "Initial pedal backup saved to {path}",
    "Primeira conexão: os 8 IRs e os 3 presets que estavam no pedal foram salvos em\n{dir}\n\n"
    "Para voltar a eles, use \"Restaurar backup de IRs…\".":
        "First connection: the 8 IRs and 3 presets that were on the pedal were saved to\n{dir}\n\n"
        "To go back to them, use \"Restore IR backup…\".",
    # Presets
    "Salvando presets…": "Saving presets…",
    "Presets salvos e conferidos no pedal.": "Presets saved and verified on the pedal.",
    "Os presets A, B e C do pedal serão substituídos pelos valores de fábrica.\n"
    "Os IRs não são alterados. Continuar?":
        "Presets A, B and C on the pedal will be replaced by the factory values.\n"
        "IRs are not changed. Continue?",
    "Restaurando presets de fábrica…": "Restoring factory presets…",
    "Presets de fábrica restaurados.": "Factory presets restored.",
    "USB Loopback ligado.": "USB Loopback on.",
    "USB Loopback desligado.": "USB Loopback off.",
    "Há alterações nos presets que não foram salvas no pedal (elas valem até desligar o pedal). "
    "Sair mesmo assim?":
        "There are preset changes not saved to the pedal (they last until the pedal is switched off). "
        "Quit anyway?",
    # IRs
    "Abrir IR (WAV)": "Open IR (WAV)",
    "Arquivos WAV (*.wav)": "WAV files (*.wav)",
    "{ch} canal(is), {rate} Hz, {bits} bits {kind}, {frames} amostras":
        "{ch} channel(s), {rate} Hz, {bits}-bit {kind}, {frames} samples",
    "Convertido de {rate} para 48000 Hz.": "Resampled from {rate} to 48000 Hz.",
    "⚠ Sem conversão: o pedal toca a 48000 Hz, o timbre fica alterado.":
        "⚠ Not resampled: the pedal plays at 48000 Hz, so the tone will change.",
    "O pedal guarda {kept:.1f} ms de {total:.1f} ms; {pct:.1f}% da energia do IR coube.":
        "The pedal keeps {kept:.1f} ms of {total:.1f} ms; {pct:.1f}% of the IR's energy fits.",
    "Gravar IR": "Write IR",
    "O IR atual do slot {n} será substituído.\nUma cópia de segurança dele será salva antes. Continuar?":
        "The current IR in slot {n} will be replaced.\nA backup copy of it will be saved first. Continue?",
    "Gravando IR no slot {n}…": "Writing IR to slot {n}…",
    "IR gravado no slot {n}. Backup do anterior: {path}": "IR written to slot {n}. Backup of the previous one: {path}",
    "Salvar backup dos IRs": "Save IR backup",
    "Backup de IRs (*.bin)": "IR backup (*.bin)",
    "Lendo os 8 IRs do pedal…": "Reading the pedal's 8 IRs…",
    "Backup salvo em {path}": "Backup saved to {path}",
    "Restaurar backup de IRs": "Restore IR backup",
    "Restaurar backup": "Restore backup",
    "Os 8 IRs do pedal serão substituídos pelo conteúdo de\n{path}\n\nContinuar?":
        "The pedal's 8 IRs will be replaced by the contents of\n{path}\n\nContinue?",
    "Não foi possível identificar o slot deste backup.": "Could not tell which slot this backup belongs to.",
    "identificado pelo nome do arquivo": "taken from the file name",
    "escolhido em 'Gravar no slot'": "chosen in 'Write to slot'",
    "Restaurar slot": "Restore slot",
    "Este é o backup de um único IR.\nEle será gravado no slot {n} ({where}).\n\nContinuar?":
        "This is a single-IR backup.\nIt will be written to slot {n} ({where}).\n\nContinue?",
    "Restaurando o slot {n}…": "Restoring slot {n}…",
    "Slot {n} restaurado. Backup do anterior: {path}": "Slot {n} restored. Backup of the previous one: {path}",
    "Localize o BCIF.bin (pasta bin do CubeSuite)": "Locate BCIF.bin (CubeSuite's bin folder)",
    "Este BCIF.bin tem tamanho inesperado; o certo é 32768 bytes.":
        "This BCIF.bin has an unexpected size; it should be 32768 bytes.",
    "IRs de fábrica copiados para {path}": "Factory IRs copied to {path}",
    "Os 8 IRs do pedal serão substituídos pelos IRs de fábrica.\n"
    "IRs personalizados serão perdidos, mas um backup completo é feito antes.\n\nContinuar?":
        "The pedal's 8 IRs will be replaced by the factory IRs.\n"
        "Custom IRs will be lost, but a full backup is made first.\n\nContinue?",
    "Arquivo com tamanho inesperado ({size} bytes). Um backup completo tem 32768 bytes (8 IRs) "
    "e o de um slot, 4096.":
        "Unexpected file size ({size} bytes). A full backup is 32768 bytes (8 IRs) and a single-slot one 4096.",
    "Gravando IRs (backup + gravação + conferência)…": "Writing IRs (backup + write + verify)…",
    "IRs gravados e conferidos. Backup anterior: {path}": "IRs written and verified. Previous backup: {path}",
    "Erro: {msg}": "Error: {msg}",
    # device.py
    "Pedal não encontrado. Ele está conectado no USB?": "Pedal not found. Is it connected via USB?",
    "Sem resposta do pedal (comando {cmd:02X})": "No response from the pedal (command {cmd:02X})",
    "Resposta de leitura inesperada": "Unexpected read response",
    "Pedal recusou a gravação (status {status})": "The pedal rejected the write (status {status})",
    # model.py
    "Modelo não suportado (id 0x{chip:04X}); este app é para o Cube Baby AC.":
        "Unsupported model (id 0x{chip:04X}); this app is for the Cube Baby AC.",
    "Bloqueado: 0x{addr:X}+{length} fora da área de IRs.": "Blocked: 0x{addr:X}+{length} is outside the IR area.",
    "Endereço de apagamento não alinhado ao setor": "Erase address is not sector-aligned",
    "Falha ao apagar setor 0x{addr:X}": "Failed to erase sector 0x{addr:X}",
    "A verificação falhou: o que foi lido do pedal difere do que foi gravado.":
        "Verification failed: what was read back from the pedal differs from what was written.",
    # ir.py
    "O arquivo não é um WAV válido (falta o cabeçalho RIFF/WAVE).":
        "The file is not a valid WAV (missing RIFF/WAVE header).",
    "WAV sem os blocos 'fmt' ou 'data'.": "WAV without 'fmt' or 'data' chunks.",
    "O WAV não tem amostras.": "The WAV has no samples.",
    "Formato WAV não suportado ({bits} bits, tipo {fmt}). Use PCM 16/24 bits ou float 32.":
        "Unsupported WAV format ({bits}-bit, type {fmt}). Use 16/24-bit PCM or 32-bit float.",
}

_TABLES = {"en": EN}
_lang = "pt"


def default_language() -> str:
    """Idioma do sistema: português se for pt_*, senão inglês."""
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            return "pt" if value.lower().startswith("pt") else "en"
    return "en"


def set_language(code: str) -> None:
    global _lang
    _lang = code if code in LANGS else "pt"


def language() -> str:
    return _lang


def T(text: str, **kw) -> str:
    out = _TABLES.get(_lang, {}).get(text, text)
    return out.format(**kw) if kw else out
