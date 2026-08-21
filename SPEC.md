# Whispers — Especificação técnica

## 1. Objetivo e escopo

Aplicativo desktop em português para Windows 10/11 x64 que transcreve um arquivo local de áudio ou vídeo por vez. A entrada pode ser escolhida no seletor do Windows ou arrastada para a janela. O resultado é um TXT, com timestamps opcionais por segmento, salvo na pasta escolhida pelo usuário dentro do aplicativo.

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
- O instalador não cria, consulta nem valida a pasta de transcrições. Ele instala somente o aplicativo, suas dependências e atalhos.
- A única solicitação obrigatória na primeira abertura é a chave da API. A pasta não é solicitada durante a inicialização.
- Ao tentar transcrever sem destino salvo, o aplicativo abre o seletor nativo do Windows. Se o usuário cancelar, a transcrição não começa.
- A pasta escolhida fica visível na tela principal, pode ser alterada a qualquer momento e é persistida por usuário.
- As tags `v0.1.5` e `v0.1.6` não serão reutilizadas. A próxima versão será `v0.1.7`.

## 3. Requisitos funcionais

- Solicitar e salvar a chave da API na primeira abertura; permitir substituí-la ou removê-la depois.
- Solicitar a pasta de destino somente quando o usuário clicar em `Transcrever` sem ter uma pasta selecionada; permitir cancelar a escolha e alterá-la depois pelo botão `Escolher pasta`.
- Exibir o caminho de destino atual na janela. A ausência de destino não bloqueia o botão `Transcrever`; o clique aciona a seleção da pasta antes de qualquer processamento ou envio.
- Aceitar os formatos comuns aprovados de áudio e vídeo, validando o conteúdo com FFprobe.
- Exibir arquivo, tamanho, duração, modo, andamento, cancelamento e mensagens de erro em português.
- Extrair e normalizar áudio com FFmpeg, dividindo entradas longas em partes abaixo do limite de 25 MB da API.
- Gerar `arquivo.txt` ou `arquivo_timestamps.txt` sem sobrescrever resultados anteriores.
- Persistir o histórico de transcrições concluídas e permitir abrir, localizar, remover e limpar entradas.
- Persistir a pasta assim que ela for escolhida e reutilizá-la nas próximas execuções sem nova solicitação ou validação preventiva.

## 4. Arquitetura e contratos

- Uma aplicação WPF com code-behind e serviços concretos, sem MVVM, DI, banco ou SDK OpenAI.
- Usar `Microsoft.Win32.OpenFolderDialog`, nativo do WPF no .NET 8, sem adicionar pacote ou dependência.
- FFmpeg converte a primeira faixa para MP3 mono, 16 kHz, 64 kbps, em partes de até 20 minutos.
- `POST https://api.openai.com/v1/audio/transcriptions` recebe cada parte sequencialmente com `language=pt`.
- Modo simples: `model=gpt-transcribe`, JSON. Modo timestamp: `model=whisper-1`, `response_format=verbose_json`, `timestamp_granularities[]=segment`.
- TXT simples concatena o texto dos chunks. TXT com timestamp usa `[HH:MM:SS] texto`, aplicando o deslocamento global do chunk.
- `%LocalAppData%\Whispers\app-state.json` contém a chave protegida, o caminho da pasta escolhida e o histórico; o conteúdo transcrito não é armazenado ali.
- `TranscriptionWorkflow.RunAsync` recebe explicitamente a pasta de destino; não existe caminho padrão nem resolução de `SpecialFolder.MyDocuments` no fluxo de saída.
- O instalador contém o payload completo de `dotnet publish --self-contained true -r win-x64`, incluindo runtime .NET/WPF, e `tools\ffmpeg.exe`/`tools\ffprobe.exe`.
- A instalação não executa gerenciadores de pacote nem baixa dependências; apenas extrai o bundle validado para `%LocalAppData%\Programs\Whispers`.

## 5. Segurança e falhas

- Proteger a chave com DPAPI `CurrentUser`, nunca exibi-la novamente nem registrá-la.
- Informar que a mídia será enviada à OpenAI antes de salvar a chave.
- Repetir até três vezes apenas falhas transitórias de rede, HTTP 429 e HTTP 5xx, respeitando `Retry-After`.
- Cancelar também o FFmpeg e requisições em andamento; sempre apagar arquivos temporários.
- Escrever o TXT de forma atômica. Falha definitiva não deixa TXT parcial nem entrada no histórico.
- Se uma pasta já selecionada ficar indisponível posteriormente, a falha normal de gravação é mostrada em português e o usuário pode escolher outro destino; não há nova seleção automática enquanto existir uma opção salva.
- Desinstalação remove chave, preferência e histórico, mas nunca remove a pasta escolhida nem os TXTs do usuário.

## 6. Aceitação, testes e distribuição

- Verificações automatizadas cobrem nomes sem colisão, timestamps, persistência/DPAPI, requisições, respostas e retries.
- Testes de mídia cobrem áudio, vídeo, ausência de faixa de áudio, formato inválido e múltiplos chunks.
- GitHub Actions compila e verifica push/PR; tags `v*` criam um único `Whispers-Setup-x64.exe` em GitHub Releases.
- O payload publicado e a instalação silenciosa devem conter, no mínimo, o executável, `.deps.json`, `.runtimeconfig.json`, `coreclr.dll`, `hostfxr.dll`, `hostpolicy.dll`, `System.Private.CoreLib.dll`, bibliotecas WPF, FFmpeg e FFprobe, todos não vazios.
- O teste do instalador deve instalá-lo em um diretório limpo e validar o payload instalado sem acessar ou criar qualquer pasta especial de documentos.
- O smoke test pós-instalação deve executar `ffmpeg.exe -version` e `ffprobe.exe -version` a partir da pasta instalada, ambos com código de saída zero.
- O smoke test deve iniciar o `Whispers.exe` instalado, confirmar que o processo permanece ativo sem encerramento imediato e então finalizá-lo de forma controlada.
- A validação deve confirmar que a publicação é self-contained e que o aplicativo instalado usa o runtime .NET empacotado, sem depender de uma instalação global do .NET.
- O fluxo de transcrição deve permanecer coberto por uma requisição simulada, sem consumo nem dependência da API durante o CI.
- As verificações cobrem persistência da pasta escolhida, geração do TXT nela e solicitação do seletor somente quando não houver destino salvo.
- O script do instalador não pode conter `{userdocs}`, `{userprofile}` nem código de criação da pasta de transcrições.
- Instalação, atualização sobre uma versão existente e desinstalação silenciosas devem terminar com código zero; a desinstalação preserva qualquer pasta de destino e os TXTs do usuário.
- O instalador inclui runtime .NET, FFmpeg/FFprobe LGPL fixados por URL imutável e SHA-256, atalhos e desinstalador; a pasta de saída não faz parte da instalação.
- A publicação do release deve informar explicitamente o repositório ao GitHub CLI e só ocorrer após build, checks, publicação self-contained e teste real do instalador concluírem com sucesso.
