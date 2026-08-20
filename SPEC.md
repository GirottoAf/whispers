# Whispers — Especificação técnica

## 1. Objetivo e escopo

Aplicativo desktop em português para Windows 10/11 x64 que transcreve um arquivo local de áudio ou vídeo por vez. A entrada pode ser escolhida no seletor do Windows ou arrastada para a janela. O resultado é um TXT em `Documentos\Whispers`, com timestamps opcionais por segmento.

Ficam fora da versão inicial: autenticação própria, backend, fila, diarização, SRT/VTT, autoatualização, versão portátil, ARM64 e seleção manual de idioma.

## 2. Suposições aprovadas

- Repositório público `GirottoAf/whispers`, licença MIT e primeira versão `v0.1.0`.
- Aplicativo WPF self-contained em .NET 8, distribuído em instalador EXE sem assinatura.
- Cada usuário fornece sua própria chave e assume a cobrança da API OpenAI.
- Sem timestamp usa `gpt-transcribe`; com timestamp usa `whisper-1`, que permanece disponível e suporta timestamps por segmento.
- Apenas a primeira faixa de áudio é usada. O idioma é detectado automaticamente.
- Atualizações são obtidas manualmente no GitHub Releases.

## 3. Requisitos funcionais

- Solicitar e salvar a chave da API na primeira abertura; permitir substituí-la ou removê-la depois.
- Aceitar os formatos comuns aprovados de áudio e vídeo, validando o conteúdo com FFprobe.
- Exibir arquivo, tamanho, duração, modo, andamento, cancelamento e mensagens de erro em português.
- Extrair e normalizar áudio com FFmpeg, dividindo entradas longas em partes abaixo do limite de 25 MB da API.
- Gerar `arquivo.txt` ou `arquivo_timestamps.txt` sem sobrescrever resultados anteriores.
- Persistir o histórico de transcrições concluídas e permitir abrir, localizar, remover e limpar entradas.

## 4. Arquitetura e contratos

- Uma aplicação WPF com code-behind e serviços concretos, sem MVVM, DI, banco ou SDK OpenAI.
- FFmpeg converte a primeira faixa para MP3 mono, 16 kHz, 64 kbps, em partes de até 20 minutos.
- `POST https://api.openai.com/v1/audio/transcriptions` recebe cada parte sequencialmente.
- Modo simples: `model=gpt-transcribe`, JSON. Modo timestamp: `model=whisper-1`, `response_format=verbose_json`, `timestamp_granularities[]=segment`.
- TXT simples concatena o texto dos chunks. TXT com timestamp usa `[HH:MM:SS] texto`, aplicando o deslocamento global do chunk.
- `%LocalAppData%\Whispers\app-state.json` contém a chave protegida e o histórico; o conteúdo transcrito não é armazenado ali.

## 5. Segurança e falhas

- Proteger a chave com DPAPI `CurrentUser`, nunca exibi-la novamente nem registrá-la.
- Informar que a mídia será enviada à OpenAI antes de salvar a chave.
- Repetir até três vezes apenas falhas transitórias de rede, HTTP 429 e HTTP 5xx, respeitando `Retry-After`.
- Cancelar também o FFmpeg e requisições em andamento; sempre apagar arquivos temporários.
- Escrever o TXT de forma atômica. Falha definitiva não deixa TXT parcial nem entrada no histórico.
- Desinstalação remove chave e histórico, mas preserva os TXTs do usuário.

## 6. Aceitação, testes e distribuição

- Verificações automatizadas cobrem nomes sem colisão, timestamps, persistência/DPAPI, requisições, respostas e retries.
- Testes de mídia cobrem áudio, vídeo, ausência de faixa de áudio, formato inválido e múltiplos chunks.
- GitHub Actions compila e verifica push/PR; tags `v*` criam `Whispers-Setup-x64.exe` em GitHub Releases.
- O instalador inclui runtime .NET, FFmpeg/FFprobe LGPL fixados por URL imutável e SHA-256, atalhos e desinstalador.
