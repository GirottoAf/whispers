# Whispers — Especificação técnica

## 1. Objetivo e escopo

Aplicativo desktop em português para Windows 10/11 x64 que transcreve um arquivo local de áudio ou vídeo por vez. A entrada pode ser escolhida no seletor do Windows ou arrastada para a janela. O resultado é um TXT em `Documentos\Whispers`, com timestamps opcionais por segmento. Se essa pasta especial estiver apontando para um local indisponível, como um redirecionamento antigo do OneDrive, o destino alternativo é `%USERPROFILE%\Documents\Whispers`.

Ficam fora da versão inicial: autenticação própria, backend, fila, diarização, SRT/VTT, autoatualização, versão portátil, ARM64 e seleção manual de idioma.

## 2. Suposições aprovadas

- Repositório público `GirottoAf/whispers`, licença MIT e primeira versão `v0.1.0`.
- Aplicativo WPF self-contained em .NET 8, distribuído em instalador EXE sem assinatura.
- Cada usuário fornece sua própria chave e assume a cobrança da API OpenAI.
- Sem timestamp usa `gpt-transcribe`; com timestamp usa `whisper-1`, que permanece disponível e suporta timestamps por segmento.
- Apenas a primeira faixa de áudio é usada. O idioma é fixo em português brasileiro (`language=pt`, conforme ISO-639-1).
- Atualizações são obtidas manualmente no GitHub Releases.

### 2.1 Suposições de trabalho desta revisão

- “Bundle” significa um único `Whispers-Setup-x64.exe` para download. Ele pode instalar vários arquivos internos, desde que nenhum runtime, codec ou utilitário precise ser baixado separadamente.
- O aplicativo instalado deve funcionar em uma instalação limpa do Windows 10/11 x64 sem .NET, FFmpeg, FFprobe, PowerShell, Python, Chocolatey ou Winget previamente instalados.
- A publicação continuará self-contained e multi-file, pois esse formato permite incluir e validar explicitamente o runtime .NET, as bibliotecas WPF e os executáveis FFmpeg/FFprobe dentro do instalador.
- O instalador e o aplicativo tentam criar `Environment.SpecialFolder.MyDocuments\Whispers`; se o caminho configurado estiver indisponível, ambos usam `%USERPROFILE%\Documents\Whispers`.
- A tag `v0.1.4` não será reutilizada porque já foi enviada e sua publicação falhou. A próxima versão será `v0.1.5`.

## 3. Requisitos funcionais

- Solicitar e salvar a chave da API na primeira abertura; permitir substituí-la ou removê-la depois.
- Aceitar os formatos comuns aprovados de áudio e vídeo, validando o conteúdo com FFprobe.
- Exibir arquivo, tamanho, duração, modo, andamento, cancelamento e mensagens de erro em português.
- Extrair e normalizar áudio com FFmpeg, dividindo entradas longas em partes abaixo do limite de 25 MB da API.
- Gerar `arquivo.txt` ou `arquivo_timestamps.txt` sem sobrescrever resultados anteriores.
- Persistir o histórico de transcrições concluídas e permitir abrir, localizar, remover e limpar entradas.
- Criar a pasta de transcrições durante a instalação, antes da primeira execução, e recriá-la automaticamente se o usuário a remover, incluindo o fallback quando Documentos estiver indisponível.

## 4. Arquitetura e contratos

- Uma aplicação WPF com code-behind e serviços concretos, sem MVVM, DI, banco ou SDK OpenAI.
- FFmpeg converte a primeira faixa para MP3 mono, 16 kHz, 64 kbps, em partes de até 20 minutos.
- `POST https://api.openai.com/v1/audio/transcriptions` recebe cada parte sequencialmente com `language=pt`.
- Modo simples: `model=gpt-transcribe`, JSON. Modo timestamp: `model=whisper-1`, `response_format=verbose_json`, `timestamp_granularities[]=segment`.
- TXT simples concatena o texto dos chunks. TXT com timestamp usa `[HH:MM:SS] texto`, aplicando o deslocamento global do chunk.
- `%LocalAppData%\Whispers\app-state.json` contém a chave protegida e o histórico; o conteúdo transcrito não é armazenado ali.
- O instalador contém o payload completo de `dotnet publish --self-contained true -r win-x64`, incluindo runtime .NET/WPF, e `tools\ffmpeg.exe`/`tools\ffprobe.exe`.
- A instalação não executa gerenciadores de pacote nem baixa dependências; apenas extrai o bundle validado para `%LocalAppData%\Programs\Whispers`.

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
- GitHub Actions compila e verifica push/PR; tags `v*` criam um único `Whispers-Setup-x64.exe` em GitHub Releases.
- O payload publicado e a instalação silenciosa devem conter, no mínimo, o executável, `.deps.json`, `.runtimeconfig.json`, `coreclr.dll`, `hostfxr.dll`, `hostpolicy.dll`, `System.Private.CoreLib.dll`, bibliotecas WPF, FFmpeg e FFprobe, todos não vazios.
- O teste do instalador deve instalá-lo em um diretório limpo, validar o payload instalado e confirmar a existência do destino preferencial ou alternativo de transcrições.
- O smoke test pós-instalação deve executar `ffmpeg.exe -version` e `ffprobe.exe -version` a partir da pasta instalada, ambos com código de saída zero.
- O smoke test deve iniciar o `Whispers.exe` instalado, confirmar que o processo permanece ativo sem encerramento imediato e então finalizá-lo de forma controlada.
- A validação deve confirmar que a publicação é self-contained e que o aplicativo instalado usa o runtime .NET empacotado, sem depender de uma instalação global do .NET.
- O fluxo de transcrição deve permanecer coberto por uma requisição simulada, sem consumo nem dependência da API durante o CI.
- Instalação, atualização sobre uma versão existente e desinstalação silenciosas devem terminar com código zero; a desinstalação preserva os TXTs em `Documentos\Whispers`.
- O instalador inclui runtime .NET, FFmpeg/FFprobe LGPL fixados por URL imutável e SHA-256, pasta de saída, atalhos e desinstalador.
- A publicação do release deve informar explicitamente o repositório ao GitHub CLI e só ocorrer após build, checks, publicação self-contained e teste real do instalador concluírem com sucesso.
