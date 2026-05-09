# cuecue 사용 설명서

`cuecue`는 `input` 폴더에 넣어 둔 음성 파일을 골라서 `faster-whisper`로 영어 음성을 글자로 바꾸고, cue 형식의 Markdown 파일로 저장하는 도구다.

결과 파일은 이런 모양으로 만들어진다.

```md
▶ 0:03 Transcribed sentence.
▶ 0:12 Next sentence.
```

각 줄의 `▶ 0:03`은 “음성의 0분 3초 지점부터 이 문장이 나온다”는 뜻이다. 뒤의 영어 문장은 전사된 내용이다.

지원하는 음성 파일 확장자는 `.aac`, `.flac`, `.m4a`, `.mp3`, `.ogg`, `.wav`, `.wma`다.

## 설치

### Python 설치

1. [python.org/downloads](https://www.python.org/downloads/)에서 최신 버전을 내려받는다.
2. 설치 중 **Add Python to PATH** 항목에 체크한다.
3. 설치가 끝나면 새 PowerShell을 열고 아래 명령으로 확인한다.

```powershell
python --version
```

`Python x.x.x`가 표시되면 된다.

### 가상 환경 만들기

`cuecue.py`가 있는 폴더에서 아래 명령을 실행한다.

```powershell
python -m venv .venv
.venv\Scripts\activate
```

프롬프트 앞에 `(.venv)`가 붙으면 가상 환경이 활성화된 것이다.

### faster-whisper 설치

가상 환경이 활성화된 상태에서 아래 명령을 실행한다.

```powershell
pip install faster-whisper
```

### ffmpeg 설치

1. [ffmpeg.org/download.html](https://ffmpeg.org/download.html)에서 Windows 빌드를 내려받는다.
2. 압축을 풀고 `bin` 폴더 안의 `ffmpeg.exe`와 `ffprobe.exe`를 PATH에 있는 폴더에 넣는다.
3. 새 PowerShell을 열고 아래 명령으로 확인한다.

```powershell
ffmpeg -version
```

### cuecue 명령으로 실행하기

`cuecue.py`가 있는 폴더에 `cuecue.cmd` 파일을 만들고 아래 내용을 넣는다.

```bat
@echo off
"%~dp0.venv\Scripts\python.exe" "%~dp0cuecue.py" %*
```

그 다음 `cuecue.cmd`가 있는 폴더를 사용자 PATH에 추가한다.

1. 시작 메뉴에서 **환경 변수 편집**을 검색해 연다.
2. **사용자 변수** 항목에서 `Path`를 선택하고 **편집**을 누른다.
3. **새로 만들기**를 누르고 `cuecue.cmd`가 있는 폴더 경로를 입력한다. 예: `C:\Users\name\cuecue`
4. 확인을 누르고 창을 닫는다.
5. 새 PowerShell을 열고 아래 명령으로 확인한다.

```powershell
cuecue
```

이후부터는 가상 환경 활성화 없이 어느 폴더에서든 `cuecue`만 입력하면 된다. `.cmd` 파일이 가상 환경의 Python을 직접 참조하기 때문이다.

## 준비

1. 전사할 음성 파일을 `input` 폴더에 넣는다.
2. 새 PowerShell 창을 연다.
3. 아래 명령을 실행한다.

```powershell
cuecue
```

`cuecue`는 기본적으로 `input` 안에서 음성 파일을 찾고, 최종 결과를 `output`에 저장한다.

## 전체 흐름

보통은 다음 순서로 진행된다.

1. 미완료 작업이 있으면 이어서 할지 새로 시작할지 고른다.
2. 새 작업이라면 전사할 음성 파일을 고른다.
3. 긴 파일은 15분 단위 청크로 나뉜다.
4. worker를 1개 쓸지 2개 쓸지 고른다.
5. 이번 실행에서 처리할 청크 수를 고른다.
6. 전사가 진행된다.
7. 모든 청크가 끝나면 하나의 Markdown 파일로 병합할지 고른다.
8. 임시 청크 파일을 보관할지 삭제할지 고른다.

영어 질문이 나오더라도 아래 설명의 “한국어 뜻”을 보고 답하면 된다.

## 파일 선택

명령을 실행하면 먼저 음성 파일 목록이 표시된다.

```text
Audio folder: C:\input
[1] lecture-a.mp3
[2] lecture-b.m4a
[3] meeting.wav

Select files (1,3, 1-4, all, q):
```

영어 질문:

```text
Select files (1,3, 1-4, all, q):
```

한국어 뜻:

```text
전사할 파일을 선택하세요. 1, 3처럼 번호를 쓰거나, 1-4처럼 범위를 쓰거나, all로 전부 선택하거나, q로 취소할 수 있습니다.
```

입력 방법:

- `1`: 1번 파일만 전사한다.
- `1,3`: 1번과 3번 파일을 전사한다.
- `1-4`: 1번부터 4번까지 전사한다.
- `all`: 목록에 있는 모든 파일을 전사한다.
- `q`: 실행을 취소한다.

여러 파일을 선택하면 한 파일이 끝난 뒤 다음 파일 전사를 시작한다. 여러 파일을 동시에 전사하지는 않는다.

잘못 입력하면 다음 메시지가 나온다.

```text
Please enter a selection, all, or q.
```

한국어 뜻:

```text
파일 번호, all, q 중 하나를 입력하세요.
```

## 미완료 작업 이어서 하기

이전에 전사하다가 중간에 종료한 작업이 있으면 파일 목록보다 먼저 미완료 작업 목록이 나온다.

```text
Unfinished jobs:
[1] lecture-a.mp3 (3/6 done, incomplete, created 2026-05-10T00:12:22)
[2] meeting.wav (4/4 done, not merged, created 2026-05-10T01:40:10)
[n] New transcription
[q] Quit
Select:
```

영어 문구와 뜻:

```text
Unfinished jobs:
```

미완료 작업 목록이라는 뜻이다.

```text
[1] lecture-a.mp3 (3/6 done, incomplete, created 2026-05-10T00:12:22)
```

`lecture-a.mp3`는 총 6개 청크 중 3개가 끝났고, 아직 완료되지 않았다는 뜻이다.

```text
[2] meeting.wav (4/4 done, not merged, created 2026-05-10T01:40:10)
```

`meeting.wav`는 청크 전사는 모두 끝났지만, 아직 최종 Markdown 파일로 병합하지 않았다는 뜻이다.

```text
[n] New transcription
```

새 전사를 시작한다는 뜻이다.

```text
[q] Quit
```

프로그램을 종료한다는 뜻이다.

```text
Select:
```

번호, `n`, `q` 중 하나를 입력하라는 뜻이다.

추천:

- 기존 작업을 이어서 하려면 해당 번호를 입력한다. 예: `1`
- 새 파일을 전사하려면 `n`을 입력한다.
- 아무것도 하지 않고 끝내려면 `q`를 입력한다.

## 기본 설정

기본 설정은 다음과 같다.

- model: `small`
- language: `en`
- device: `cpu`
- compute type: `int8`
- chunk size: 15분

영어 음성을 전사하는 설정이다. 다른 언어를 자동으로 고르는 도구가 아니라, 현재 코드는 `language: en`으로 고정되어 있다.

최종 출력은 기본적으로 `C:\Desana\output` 폴더에 저장된다.

- 최종 병합 파일: `example.md`
- 같은 이름이 이미 있으면: `example (1).md`, `example (2).md`, ...

## 긴 파일 처리

파일 길이가 15분 이상이면 `cuecue`는 먼저 파일을 15분 단위로 나눈다. 나뉜 각각의 파일을 “청크”라고 부른다.

예를 들어 1시간 20분짜리 파일은 다음처럼 나뉜다.

- 15분 청크 5개
- 5분 청크 1개

모든 청크가 끝나면 하나의 Markdown 파일로 합칠지 묻는다.

임시 청크와 중간 전사 결과는 `cuecue\temp_chunks` 안에 작업별로 저장된다.

예:

```text
cuecue\temp_chunks\20260510-001222-example\chunks\chunk_001.mp3
cuecue\temp_chunks\20260510-001222-example\partial\chunk_001.md
```

중간에 PowerShell을 닫거나 컴퓨터를 끄더라도, 다음 실행에서 미완료 작업을 선택해 이어서 처리할 수 있다.

## worker 선택

전사를 시작하면 다음 질문이 나온다.

```text
Use two workers for faster processing? This may increase heat and fan noise. (y/n):
```

한국어 뜻:

```text
더 빠르게 처리하기 위해 worker 2개를 사용할까요? 컴퓨터 발열과 팬 소음이 늘어날 수 있습니다. y 또는 n으로 답하세요.
```

입력 방법:

- `y`: worker 2개를 사용한다. 더 빠를 수 있지만 CPU를 더 많이 쓰고 팬 소음이 커질 수 있다.
- `n`: worker 1개만 사용한다. 더 느릴 수 있지만 안정적이고 부담이 적다.

추천:

- 노트북이 뜨겁거나 다른 작업도 같이 해야 하면 `n`
- 빠르게 끝내고 싶고 팬 소음이 괜찮으면 `y`

잘못 입력하면 다음 메시지가 나온다.

```text
Please enter y or n.
```

한국어 뜻:

```text
y 또는 n만 입력하세요.
```

## 이번 실행에서 처리할 청크 수 제한

worker를 고른 뒤 다음 질문이 나온다.

```text
Limit chunks per worker for this run? Type a number, or all to process all remaining chunks:
```

한국어 뜻:

```text
이번 실행에서 worker 하나당 처리할 청크 수를 제한할까요? 숫자를 입력하거나, 남은 청크를 전부 처리하려면 all을 입력하세요.
```

입력 방법:

- `all`: 남은 청크를 전부 처리한다.
- `1`: worker 하나당 청크 1개만 처리한다.
- `2`: worker 하나당 청크 2개만 처리한다.

예를 들어 worker 2개를 사용하고 여기서 `1`을 입력하면, 이번 실행에서는 최대 2개 청크만 처리한다. worker 1개를 사용하고 `1`을 입력하면, 이번 실행에서는 1개 청크만 처리한다.

추천:

- 끝까지 돌려도 괜찮으면 `all`
- 테스트로 조금만 돌려보고 싶으면 `1`
- 컴퓨터를 오래 켜두기 어렵다면 작은 숫자

잘못 입력하면 다음 메시지가 나온다.

```text
Please enter a positive number or all.
```

한국어 뜻:

```text
1 이상의 숫자 또는 all을 입력하세요.
```

## 진행 중 표시

청크 하나가 끝날 때마다 다음처럼 진행 상황이 표시된다.

```text
Chunk 2 completed (2/6 done)
Started: 00:12:30
Completed: 00:18:42
Chunk elapsed: 00:06:12
File elapsed: 00:12:20
```

한국어 뜻:

- `Chunk 2 completed`: 2번 청크가 끝났다.
- `(2/6 done)`: 전체 6개 중 2개가 끝났다.
- `Started`: 이 청크 전사를 시작한 시각이다.
- `Completed`: 이 청크 전사가 끝난 시각이다.
- `Chunk elapsed`: 이 청크 하나를 처리하는 데 걸린 시간이다.
- `File elapsed`: 이 파일 작업을 시작한 뒤 지금까지 걸린 전체 시간이다.

## 불확실한 중간 결과 처리

이전 실행이 중간에 종료되면, 어떤 청크는 파일이 만들어졌지만 완료 표시가 안 되어 있을 수 있다. 이때 다음 안내가 나온다.

```text
Some partial results exist but are not marked complete.
These files may be incomplete if the previous run stopped while writing.

[3] chunk_003.md  12 KB  modified 2026-05-10 00:30
Select chunks to keep as completed. Use numbers like 3,5 or 3-5; none = reprocess all; all = keep all:
```

영어 질문:

```text
Select chunks to keep as completed. Use numbers like 3,5 or 3-5; none = reprocess all; all = keep all:
```

한국어 뜻:

```text
완료된 것으로 인정할 청크를 고르세요. 3,5처럼 번호를 쓰거나, 3-5처럼 범위를 쓸 수 있습니다. none은 전부 다시 처리, all은 전부 완료로 인정한다는 뜻입니다.
```

입력 방법:

- `all`: 표시된 중간 결과를 모두 완료된 것으로 인정한다.
- `none`: 표시된 중간 결과를 모두 믿지 않고 다시 전사한다.
- `3`: 3번 청크만 완료된 것으로 인정한다.
- `3,5`: 3번과 5번 청크를 완료된 것으로 인정한다.
- `3-5`: 3번부터 5번까지 완료된 것으로 인정한다.

추천:

- 이전 실행이 정상적으로 청크를 끝낸 직후 멈춘 것 같으면 `all`
- 이전 실행이 전사 중에 갑자기 꺼졌다면 `none`
- 잘 모르겠으면 `none`이 안전하다. 시간이 더 걸리지만 깨진 중간 결과를 쓰지 않는다.

## 병합하기

모든 청크 전사가 끝나면 다음 질문이 나온다.

```text
All chunks are complete.
Merge them into one Markdown file now? (y/n):
```

영어 질문:

```text
Merge them into one Markdown file now? (y/n):
```

한국어 뜻:

```text
완료된 청크 결과들을 지금 하나의 Markdown 파일로 합칠까요? y 또는 n으로 답하세요.
```

입력 방법:

- `y`: 하나의 최종 Markdown 파일을 만든다.
- `n`: 지금은 합치지 않고 임시 작업 폴더를 그대로 둔다.

추천:

- 보통은 `y`를 입력하면 된다.
- 중간 결과를 직접 확인하고 나중에 합치고 싶으면 `n`을 입력한다.

병합이 끝나면 다음처럼 최종 파일 위치가 표시된다.

```text
Merged output: C:\Desana\output\example.md
```

한국어 뜻:

```text
최종 Markdown 파일이 C:\output\example.md에 만들어졌습니다.
```

## 임시 청크 파일 보관

병합 후 다음 질문이 나온다.

```text
Keep temporary chunks and partial results? (y/n):
```

한국어 뜻:

```text
임시 청크 파일과 중간 전사 결과를 보관할까요? y 또는 n으로 답하세요.
```

입력 방법:

- `y`: `cuecue\temp_chunks` 안의 임시 파일을 남긴다.
- `n`: 임시 파일을 삭제한다.

추천:

- 최종 Markdown 파일만 필요하면 `n`
- 나중에 청크별 결과를 확인하거나 문제를 분석해야 하면 `y`

`n`을 입력하면 다음 메시지가 나온다.

```text
Temporary chunks and partial results removed.
```

한국어 뜻:

```text
임시 청크와 중간 결과를 삭제했습니다.
```

## 출력 폴더 지정

기본 출력 폴더인 `C:\output` 대신 다른 폴더에 최종 Markdown 파일을 저장하려면 `-o` 옵션을 쓴다.

```powershell
cuecue -o C:\path\to\out
```

예:

```powershell
cuecue -o C:\Users\name\Desktop\transcripts
```

이렇게 실행하면 최종 Markdown 파일이 `C:\Users\name\Desktop\transcripts`에 저장된다.

## 청크 길이 변경

기본 청크 길이는 15분이다. 10분 단위로 나누고 싶으면 `--chunk-minutes` 옵션을 쓴다.

```powershell
cuecue --chunk-minutes 10
```

청크를 짧게 하면 한 청크가 실패했을 때 다시 처리할 양이 줄어든다. 대신 청크 파일 개수가 늘어난다.

추천:

- 일반 사용: 기본값 15분
- 자주 멈추는 환경: 5분 또는 10분
- 긴 파일을 한 번에 안정적으로 처리하는 환경: 15분 그대로

## 자주 생기는 문제

### `cuecue` 명령을 찾을 수 없는 경우

새 PowerShell을 열어 다시 시도한다. 그래도 안 되면 cuecue.pu가 들어 있는 폴더가 사용자 PATH에 들어 있는지 확인한다.

### `Audio folder not found: C:\input`

`C:\input` 폴더가 없다는 뜻이다. 폴더를 만든 뒤 음성 파일을 넣고 다시 실행한다.

### `No audio files found in C:\input`

`C:\input` 폴더는 있지만, 지원하는 확장자의 음성 파일이 없다는 뜻이다.

지원 확장자는 `.aac`, `.flac`, `.m4a`, `.mp3`, `.ogg`, `.wav`, `.wma`다.

### `No matching distribution found for fast-whisper`

패키지 이름은 `fast-whisper`가 아니라 `faster-whisper`다.

```powershell
pip install faster-whisper
```

### `Missing required tool: ffmpeg` 또는 `Missing required tool: ffprobe`

ffmpeg가 설치되어 있지 않거나 PATH에 없다는 뜻이다. ffmpeg를 설치한 뒤 새 PowerShell을 열고 다시 실행한다.

### Python 3.14에서 설치가 안 되는 경우

`faster-whisper` 또는 관련 의존성이 Python 3.14 wheel을 아직 제공하지 않을 수 있다. 이 경우 Python 3.11 또는 3.12 환경에서 실행하는 편이 안전하다.

### 전사 중에 PowerShell을 닫은 경우

다시 `cuecue`를 실행하면 미완료 작업 목록이 나온다. 이어서 하려면 해당 작업 번호를 입력한다.

중간 결과가 불확실하다는 질문이 나오면, 잘 모르겠을 때는 `none`을 입력해 다시 처리하는 편이 안전하다.
