from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional
import re
import json

# Try to import requests for Ollama API
try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


# ===== Data Structures =====

Role = Literal["presenter", "questioner"]  # Presenter / Questioner


@dataclass
class Utterance:
    role: Role
    text: str


@dataclass
class QAPair:
    question: str
    answer: str


# ===== Q/A Pair Builder =====

class QAPairBuilder:
    """
    Builds Q/A pairs from chronological utterance list.
    Groups consecutive questioner utterances -> consecutive presenter utterances.
    """

    def build_pairs(self, utterances: List[Utterance]) -> List[QAPair]:
        pairs: List[QAPair] = []
        i = 0
        n = len(utterances)

        while i < n:
            # Skip non-questioner utterances
            if utterances[i].role != "questioner":
                i += 1
                continue

            # 1) Group consecutive questioner utterances
            q_texts: List[str] = []
            while i < n and utterances[i].role == "questioner":
                t = utterances[i].text.strip()
                if t:
                    q_texts.append(t)
                i += 1

            if not q_texts:
                continue

            # 2) Group consecutive presenter utterances (answers)
            a_texts: List[str] = []
            while i < n and utterances[i].role == "presenter":
                t = utterances[i].text.strip()
                if t:
                    a_texts.append(t)
                i += 1

            # Skip if no answer
            if not a_texts:
                continue

            q = " ".join(q_texts)
            a = " ".join(a_texts)

            pairs.append(QAPair(question=q, answer=a))

        return pairs


# ===== Simple Rule-Based Summarizer (Fallback) =====

class SimpleSentenceSummarizer:
    """
    Extractive summarizer that:
    - Splits text by sentence boundaries
    - Keeps the most informative sentences
    """

    def __init__(self, max_sentences: int = 2, max_chars: int = 250) -> None:
        self.max_sentences = max_sentences
        self.max_chars = max_chars

    def summarize(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""

        # Return as-is if short enough
        if len(text) <= self.max_chars:
            return text

        # Sentence splitting
        sentences = re.split(r'(?<=[.!?。])\s+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return text[:self.max_chars] + "..."

        # If few sentences, return all
        if len(sentences) <= self.max_sentences:
            return " ".join(sentences)

        # Return first N sentences (usually contains the key info)
        result = " ".join(sentences[:self.max_sentences])
        if len(result) > self.max_chars:
            result = result[:self.max_chars].rsplit(" ", 1)[0] + "..."

        return result


# ===== Ollama LLM Summarizer =====

class OllamaSummarizer:
    """
    Summarizer using local Ollama LLM.
    Provides high-quality abstractive summarization for Q&A contexts.
    """

    # Optimized system prompt for better summarization
    SYSTEM_PROMPT = """당신은 전문 회의록 요약가입니다. 발표자의 답변을 정확하고 간결하게 요약합니다.

## 요약 원칙
1. 핵심 정보를 빠짐없이 포함 (기술명, 수치, 조건 등)
2. 1-2문장으로 압축하되, 중요한 세부사항은 유지
3. 원문에 없는 내용을 추가하지 않음
4. "~입니다", "~합니다" 등 존댓말로 마무리
5. 요약문만 출력 (다른 설명이나 서문 없이)"""

    def __init__(
        self,
        model: str = "gemma2:9b",
        base_url: str = "http://localhost:11434",
        timeout: int = 60,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.simple = SimpleSentenceSummarizer()
        self.enabled = False

        if not _HAS_REQUESTS:
            print("[WARN] requests module not found. Using simple summarizer.")
            return

        # Check if Ollama is available
        try:
            resp = requests.get(f"{base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                # Check if requested model is available (handle both "gemma2:2b" and "gemma2:2b-instruct" formats)
                model_base = model.split(":")[0]
                if any(model_base in m for m in models):
                    self.enabled = True
                    print(f"[INFO] Ollama summarizer enabled (model: {model})")
                else:
                    print(f"[WARN] Model '{model}' not found. Available: {models}")
                    print(f"[INFO] Run 'ollama pull {model}' to install.")
            else:
                print("[WARN] Ollama server not responding properly.")
        except requests.exceptions.ConnectionError:
            print("[WARN] Ollama server not running. Using simple summarizer.")
        except Exception as e:
            print(f"[WARN] Ollama check failed: {e}")

    def summarize(self, text: str, max_tokens: int = 150) -> str:
        """Summarize text using Ollama LLM."""
        text = text.strip()
        if not text:
            return ""

        # Short text doesn't need summarization
        if len(text) < 80:
            return text

        if not self.enabled:
            return self.simple.summarize(text)

        try:
            prompt = f"""[답변 원문]
{text}

[요약]"""

            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "system": self.SYSTEM_PROMPT,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": 0.2,
                        "top_p": 0.85,
                        "top_k": 40,
                    }
                },
                timeout=self.timeout,
            )

            if response.status_code == 200:
                result = response.json().get("response", "").strip()
                # Clean up the result
                result = self._clean_output(result)
                if result:
                    return result

            return self.simple.summarize(text)

        except requests.exceptions.Timeout:
            print("[WARN] Ollama request timed out. Using simple summarizer.")
            return self.simple.summarize(text)
        except Exception as e:
            print(f"[WARN] Ollama summarization failed: {e}")
            return self.simple.summarize(text)

    def _clean_output(self, text: str) -> str:
        """Clean up LLM output."""
        # Remove common prefixes
        prefixes_to_remove = [
            "요약:", "요약 :", "답변 요약:", "요약문:",
            "Summary:", "Answer:",
        ]
        for prefix in prefixes_to_remove:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()

        # Remove quotes if present
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        if text.startswith("'") and text.endswith("'"):
            text = text[1:-1]

        return text.strip()


# ===== Q/A Summary Pipeline =====

class QASummaryGenerator:
    def __init__(
        self,
        qa_builder: QAPairBuilder,
        summarizer: OllamaSummarizer,
        max_question_chars: int = 150,
        debug: bool = False,
    ) -> None:
        self.qa_builder = qa_builder
        self.summarizer = summarizer
        self.max_question_chars = max_question_chars
        self.debug = debug

    def _summarize_question(self, q: str) -> str:
        """
        Summarize question using LLM to preserve all key topics.
        - If short enough, return as-is
        - Otherwise, use LLM to extract the core question(s)
        """
        q = q.strip()
        if not q:
            return q

        # Short question - return as-is
        if len(q) <= self.max_question_chars:
            return q

        # Use LLM to summarize the question while preserving all topics
        if self.summarizer.enabled:
            try:
                prompt = f"""[질문 원문]
{q}

[요약]"""

                # Question-specific system prompt
                q_system = """당신은 질문 요약 전문가입니다. 여러 문장으로 된 질문을 핵심만 남겨 간결하게 요약합니다.

## 요약 원칙
1. 질문의 모든 주제를 빠짐없이 포함
2. "~인가요?", "~할까요?" 등 질문 형태 유지
3. 불필요한 말(아, 근데, 그러니까, 잠깐만요 등) 제거
4. 1-2문장으로 압축
5. 요약문만 출력 (다른 설명 없이)"""

                response = requests.post(
                    f"{self.summarizer.base_url}/api/generate",
                    json={
                        "model": self.summarizer.model,
                        "prompt": prompt,
                        "system": q_system,
                        "stream": False,
                        "options": {
                            "num_predict": 100,
                            "temperature": 0.2,
                            "top_p": 0.85,
                            "top_k": 40,
                        }
                    },
                    timeout=30,
                )

                if response.status_code == 200:
                    result = response.json().get("response", "").strip()
                    result = self.summarizer._clean_output(result)
                    if result:
                        return result
            except Exception:
                pass

        # Fallback: keep sentences with question marks, remove filler words
        return self._extract_key_question(q)

    def _extract_key_question(self, q: str) -> str:
        """Fallback: extract key question without LLM"""
        # Remove common filler words/phrases
        fillers = [
            r'^아\s+', r'^어\s+', r'^음\s+', r'^그\s+',
            r'근데요?\s*', r'그러니까\s*', r'잠깐만요?\s*',
            r'있잖아요?\s*', r'그거\s+', r'뭐냐\s*',
            r'아까\s+말씀하신\s+', r'좀\s+다른\s+얘긴데\s*',
        ]

        result = q
        for filler in fillers:
            result = re.sub(filler, '', result, flags=re.IGNORECASE)

        result = result.strip()

        # If still too long, try to keep question sentences
        if len(result) > self.max_question_chars:
            sentences = re.split(r'(?<=[?？.!])\s+', result)
            q_sentences = [s for s in sentences if '?' in s or '？' in s]
            if q_sentences:
                result = ' '.join(q_sentences)

        if len(result) > self.max_question_chars:
            result = result[:self.max_question_chars].rsplit(' ', 1)[0] + '...'

        return result

    def summarize_dialogue(self, utterances: List[Utterance]) -> str:
        pairs = self.qa_builder.build_pairs(utterances)

        if self.debug:
            print(f"[DEBUG] 빌드된 Q/A 쌍 개수: {len(pairs)}")
            for idx, p in enumerate(pairs, start=1):
                print(f"[DEBUG] Q{idx}-원문: {p.question}")
                print(f"[DEBUG] A{idx}-원문: {p.answer}")

        if not pairs:
            return "(Q/A 쌍이 하나도 만들어지지 않았습니다. role 값이 'questioner' / 'presenter'인지 확인하세요.)"

        lines: List[str] = []
        for i, pair in enumerate(pairs, start=1):
            # Q: summarize question (preserving all topics)
            q_summary = self._summarize_question(pair.question)

            # A: summarize with LLM
            a_summary = self.summarizer.summarize(pair.answer)
            if not a_summary:
                a_summary = pair.answer.strip()

            lines.append(f"- Q{i}: {q_summary}")
            lines.append(f"  A{i}: {a_summary}")

        return "\n".join(lines)


# ===== Helper Function for External Use =====

def summarize_qa_bullets(
    utterances: List[Utterance],
    debug: bool = False,
    model: str = "gemma2:2b"
) -> str:
    """
    Summarize STT results (presenter/questioner utterance list) into:
    - Qn: ...
      An: ...
    format string.
    """
    qa_builder = QAPairBuilder()
    summarizer = OllamaSummarizer(model=model)
    qa_summary = QASummaryGenerator(qa_builder, summarizer, debug=debug)
    return qa_summary.summarize_dialogue(utterances)


# ===== Demo with Sample Data =====

if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    # Extended demo set: Simulating STT results
    utterances = [
        # --- Introduction (presenter only, not included in Q/A) ---
        Utterance(
            role="presenter",
            text="오늘은 로컬 GPU 위에서 돌아가는 실시간 음성 인식과 Q&A 요약 시스템의 전체 구조를 설명드리겠습니다.",
        ),
        Utterance(
            role="presenter",
            text="지금 데모에서는 NVIDIA RTX 4090 GPU 한 장을 사용하고 있고, Whisper large-v3 모델을 기반으로 하고 있습니다.",
        ),

        # --- Q/A 1: Offline operation ---
        Utterance(
            role="questioner",
            text="질문 있습니다. 이 시스템은 인터넷 없이도 완전히 오프라인으로 동작하나요?",
        ),
        Utterance(
            role="questioner",
            text="발표 자료를 회사 외부로 내보내면 안 되는 보안 이슈가 있어서 그 부분이 중요합니다.",
        ),
        Utterance(
            role="presenter",
            text="네, 음성 인식 모델과 요약 모델 둘 다 로컬 GPU에 올려두면 네트워크 연결 없이 동작합니다.",
        ),
        Utterance(
            role="presenter",
            text="초기 모델 다운로드 단계만 인터넷이 필요하고, 그 이후에는 완전히 오프라인 환경에서도 사용할 수 있습니다.",
        ),

        # --- 2번째 Q/A: 한/영 인식 성능 ---
        Utterance(
            role="questioner",
            text="영어랑 한국어가 섞인 발화도 잘 인식되는지 궁금합니다.",
        ),
        Utterance(
            role="questioner",
            text="예를 들어 이런 식으로, 한국어로 설명하다가 suddenly I speak in English 같은 경우요.",
        ),
        Utterance(
            role="presenter",
            text="Whisper large-v3 기준으로 한국어와 영어 모두 꽤 높은 인식률을 보입니다.",
        ),
        Utterance(
            role="presenter",
            text="다만 한 문장 안에서 언어를 너무 자주 바꾸면 오인식이 조금 늘어날 수 있고, 그럴 때는 문장을 조금 더 분리해서 말해 주시면 정확도가 올라갑니다.",
        ),

        # --- 3번째 Q/A: 실시간 vs 버튼 기반 ---
        Utterance(
            role="questioner",
            text="실시간 자막처럼 계속 따라오는 기능도 가능한가요, 아니면 버튼 기반으로만 사용하는 건가요?",
        ),
        Utterance(
            role="presenter",
            text="실시간 스트리밍 모드도 구현할 수 있지만, 정확도와 지연 시간 사이의 트레이드오프가 있습니다.",
        ),
        Utterance(
            role="presenter",
            text="현재 데모에서는 버튼으로 녹음 구간을 명확하게 자른 다음, 그 구간 전체를 한 번에 인식해서 안정적인 결과를 얻는 방식을 사용하고 있습니다.",
        ),

        # --- 4번째 Q/A: 최종 요약 포맷 ---
        Utterance(
            role="questioner",
            text="최종 요약은 어떤 형식으로 나오나요?",
        ),
        Utterance(
            role="questioner",
            text="나중에 회의록으로 공유할 때 바로 붙여 넣을 수 있으면 좋겠습니다.",
        ),
        Utterance(
            role="presenter",
            text="질문자와 발표자의 발화를 묶어서 Q와 A 한 쌍으로 만들고, 각각을 요약 모델로 한두 문장씩 축약합니다.",
        ),
        Utterance(
            role="presenter",
            text="그 결과를 Q: 와 A: 로 시작하는 개조식 리스트로 출력해서 바로 문서나 메일에 붙여 넣을 수 있게 구성했습니다.",
        ),

        # --- 5번째 Q/A: 요약 길이/디테일 조절 ---
        Utterance(
            role="questioner",
            text="요약이 너무 길거나 너무 짧게 나오는 경우에는 어떻게 조절하나요?",
        ),
        Utterance(
            role="questioner",
            text="질문은 짧게, 답변은 조금 더 자세하면 좋겠습니다.",
        ),
        Utterance(
            role="presenter",
            text="요약 모델의 max_length나 num_beams 같은 하이퍼파라미터를 조절해서 길이와 디테일을 조정할 수 있습니다.",
        ),
        Utterance(
            role="presenter",
            text="또한 질문과 답변 각각에 대해 최대 토큰 수를 다르게 설정해서, 질문은 짧게, 답변은 조금 더 구체적으로 나오도록 튜닝할 수 있습니다.",
        ),

        # --- 6번째 Q/A: 저장 / 내보내기 ---
        Utterance(
            role="questioner",
            text="생성된 요약 결과는 어디에 저장되나요?",
        ),
        Utterance(
            role="questioner",
            text="텍스트 파일이나 노션 같은 곳으로 바로 옮기고 싶은데 가능할까요?",
        ),
        Utterance(
            role="presenter",
            text="지금 데모 코드에서는 우선 콘솔에 출력하지만, 동일한 문자열을 그대로 텍스트 파일이나 Markdown 파일로 저장할 수 있습니다.",
        ),
        Utterance(
            role="presenter",
            text="REST API 형태로 감싸면 노션이나 사내 위키에 자동으로 업로드하는 것도 어렵지 않습니다.",
        ),

        # --- 7번째 Q/A: 발화자 태깅 / 패널 확장 ---
        Utterance(
            role="questioner",
            text="지금은 발표자와 질문자 두 역할만 있지만, 나중에 여러 명의 발표자나 패널 토론처럼 확장하는 것도 가능할까요?",
        ),
        Utterance(
            role="presenter",
            text="네, Utterance 구조에 role 필드를 이미 넣어두었기 때문에, 역할 타입만 늘려 주면 패널 A, 패널 B 같은 식으로 확장할 수 있습니다.",
        ),
        Utterance(
            role="presenter",
            text="Q/A 매칭 로직만 약간 수정해서, 특정 발표자의 답변만 별도로 모아서 요약하는 기능 같은 것도 구현할 수 있습니다.",
        ),

        # --- 8번째 Q/A: 다국어 요약 ---
        Utterance(
            role="questioner",
            text="영어로 된 질문과 답변도 한국어로 번역해서 요약할 수 있나요?",
        ),
        Utterance(
            role="questioner",
            text="혹은 반대로 한국어 Q/A를 영어로 요약하는 시나리오도 고려하고 있습니다.",
        ),
        Utterance(
            role="presenter",
            text="현재 데모에서는 한국어 요약용 모델을 사용하고 있어서, 한국어 비중이 높을 때 가장 좋은 품질을 보입니다.",
        ),
        Utterance(
            role="presenter",
            text="영어 질문을 한국어로 번역해서 요약하거나, 영어 요약 모델을 추가로 붙이는 방식으로 멀티 언어 요약도 확장 가능합니다.",
        ),

        # --- 9번째 Q/A: 모델 업데이트 / 버전 관리 ---
        Utterance(
            role="questioner",
            text="Whisper 모델이나 요약 모델이 업데이트되었을 때 버전 관리는 어떻게 하나요?",
        ),
        Utterance(
            role="presenter",
            text="모델 파일 경로와 버전을 설정 파일로 분리해두고, 특정 회의에서는 특정 버전을 사용하도록 고정할 수 있습니다.",
        ),
        Utterance(
            role="presenter",
            text="또한 요약 결과에 사용한 모델 버전을 메타데이터로 같이 저장해 두면, 나중에 품질 비교나 회귀 테스트를 할 때 도움이 됩니다.",
        ),

        # --- 10번째 Q/A: 지연 시간/성능 튜닝 ---
        Utterance(
            role="questioner",
            text="지연 시간이 중요한 실시간 서비스에 붙일 때는 어떤 식으로 튜닝하는 게 좋을까요?",
        ),
        Utterance(
            role="presenter",
            text="Whisper 쪽에서는 모델 크기를 조절하거나 beam size를 줄이고, 요약 쪽에서는 max_length와 num_beams를 줄여서 속도를 확보할 수 있습니다.",
        ),
        Utterance(
            role="presenter",
            text="4090처럼 여유 있는 GPU에서는 large-v3와 KoBART 조합도 충분히 실시간에 가깝게 운용 가능합니다.",
        ),

        # --- 11번째 Q/A: 에러/실패 케이스 ---
        Utterance(
            role="questioner",
            text="음성 인식이 실패하거나 요약 모델이 에러를 낼 때는 어떻게 처리되나요?",
        ),
        Utterance(
            role="presenter",
            text="STT 쪽에서 텍스트가 비어 있으면 Q/A 쌍을 만들지 않고 건너뜁니다.",
        ),
        Utterance(
            role="presenter",
            text="요약 모델에서 예외가 발생하면 단순 문장 자르기 방식으로 fallback 해서, 최소한 사람이 읽을 수 있는 형태의 결과는 항상 남도록 설계했습니다.",
        ),

        # --- 12번째 Q/A: 보안/프라이버시 ---
        Utterance(
            role="questioner",
            text="회의 내용이 민감한 경우에도 이 시스템을 사용할 수 있을까요?",
        ),
        Utterance(
            role="presenter",
            text="음성 인식과 요약 모델을 모두 로컬에서 돌리고, 외부 서버로 전송하지 않으면 데이터는 사내 환경에만 머무르게 됩니다.",
        ),
        Utterance(
            role="presenter",
            text="로그 저장 경로나 암호화 정책을 사내 규정에 맞춰 설정하면, 보안/프라이버시 요구사항도 충분히 만족시킬 수 있습니다.",
        ),
    ]

    print("\n===== 기본 테스트 (12개 Q/A) =====")
    result = summarize_qa_bullets(utterances, debug=False, model="gemma2:9b")
    print(result)
    print("================================\n")

    # ===== 까다로운 테스트 케이스 =====
    difficult_utterances = [
        # Q1: 중구난방 질문 - 여러 주제가 뒤섞임
        Utterance(
            role="questioner",
            text="아 근데요 그거 있잖아요 아까 말씀하신 그 뭐냐 오프라인 되는 거",
        ),
        Utterance(
            role="questioner",
            text="그거랑 좀 다른 얘긴데 혹시 이거 맥에서도 돌아가요? 윈도우만 되는 건가요?",
        ),
        Utterance(
            role="questioner",
            text="아 그리고 메모리는 얼마나 필요해요? GPU 없으면 안 되나요?",
        ),
        Utterance(
            role="presenter",
            text="아 네 여러 가지 질문을 주셨네요. 일단 맥 지원 여부부터 말씀드리면, 현재는 Windows 환경에서 테스트했고요, macOS에서도 Python과 PyTorch가 동작하니까 기본적으로는 돌아갑니다.",
        ),
        Utterance(
            role="presenter",
            text="다만 macOS에서는 CUDA가 없어서 MPS 백엔드를 써야 하는데, Whisper는 MPS에서도 잘 돌아가요. 메모리는 Whisper large-v3 기준으로 VRAM 8GB 이상 권장하고요, CPU로도 돌릴 수는 있는데 속도가 많이 느려집니다.",
        ),

        # Q2: 불완전한 문장과 말 끊김
        Utterance(
            role="questioner",
            text="그니까 제가 궁금한 건... 아 잠깐만요",
        ),
        Utterance(
            role="questioner",
            text="네 그러니까 이게 실시간으로 막 번역도 되고 그런 건가요? 통역?",
        ),
        Utterance(
            role="questioner",
            text="동시통역 같은 거요 그런 것도 가능한지",
        ),
        Utterance(
            role="presenter",
            text="아 동시통역 기능은 현재 버전에는 포함되어 있지 않습니다.",
        ),
        Utterance(
            role="presenter",
            text="지금은 음성을 텍스트로 바꾸는 STT만 지원하고요, 번역은 별도 모듈을 붙여야 합니다. 근데 기술적으로는 가능해요. Whisper가 다국어를 지원하니까, 한국어 음성을 영어 텍스트로 바로 뽑는 것도 Whisper 옵션으로 되긴 합니다.",
        ),

        # Q3: 전문 용어와 약어가 섞인 복잡한 질문
        Utterance(
            role="questioner",
            text="ONNX로 export해서 TensorRT 최적화 적용하면 latency 줄일 수 있을 것 같은데 그런 optimization pipeline 고려하고 계신가요?",
        ),
        Utterance(
            role="questioner",
            text="아니면 quantization이라든지 pruning 같은 model compression technique도요",
        ),
        Utterance(
            role="presenter",
            text="좋은 질문입니다. 현재는 faster-whisper를 쓰고 있는데, 이게 이미 CTranslate2 기반이라 INT8 quantization이 적용되어 있어요.",
        ),
        Utterance(
            role="presenter",
            text="TensorRT 적용은 검토 중인데, 아직 Whisper 아키텍처에 대한 공식 TensorRT 지원이 제한적이에요. ONNX export는 가능하고, 실제로 해보니까 약 1.3배 정도 빨라지더라고요. 다만 accuracy가 살짝 떨어지는 trade-off가 있습니다.",
        ),

        # Q4: 감정이 섞인 부정적 피드백 + 질문
        Utterance(
            role="questioner",
            text="솔직히 데모 보니까 인식률이 좀 아쉬운 것 같아요 제가 써본 다른 서비스보다 못한 느낌?",
        ),
        Utterance(
            role="questioner",
            text="특히 마이크 품질이 안 좋으면 엉망이 되던데 이건 어떻게 개선할 계획인가요",
        ),
        Utterance(
            role="presenter",
            text="네 피드백 감사합니다. 마이크 품질에 민감한 건 사실이에요. 몇 가지 개선 방안을 말씀드리면, 첫째로 VAD(Voice Activity Detection)를 더 정교하게 튜닝할 예정이고요.",
        ),
        Utterance(
            role="presenter",
            text="둘째로 노이즈 캔슬링 전처리를 추가하려고 합니다. RNNoise 같은 걸 앞단에 붙이면 마이크 품질이 낮아도 인식률이 많이 올라가요. 실제로 내부 테스트에서 15% 정도 WER이 개선됐습니다.",
        ),

        # Q5: 매우 긴 답변 (여러 포인트)
        Utterance(
            role="questioner",
            text="이 시스템을 우리 회사에 도입하려면 어떤 준비가 필요할까요?",
        ),
        Utterance(
            role="presenter",
            text="도입을 위해서는 몇 가지 준비사항이 있습니다. 하드웨어 측면에서는 NVIDIA GPU가 탑재된 서버가 필요하고, 최소 RTX 3060 이상을 권장합니다. RTX 4090이면 가장 좋고요.",
        ),
        Utterance(
            role="presenter",
            text="소프트웨어 환경은 Python 3.9 이상, CUDA 11.8 이상이 필요합니다. Docker 환경도 제공하니까 컨테이너로 배포하시면 환경 구성이 편해요.",
        ),
        Utterance(
            role="presenter",
            text="보안 측면에서는 완전 오프라인 운영이 가능하니까 망분리 환경에서도 사용할 수 있고요. 다만 초기 모델 다운로드 때만 인터넷이 필요합니다.",
        ),
        Utterance(
            role="presenter",
            text="라이선스는 연구/교육 목적으로는 무료이고, 상업적 사용 시 별도 문의해주시면 됩니다. 기술 지원도 제공하고 있어요.",
        ),
    ]

    print("\n===== 까다로운 테스트 (5개 Q/A) =====")
    result2 = summarize_qa_bullets(difficult_utterances, debug=True, model="gemma2:9b")
    print(result2)
    print("================================\n")
