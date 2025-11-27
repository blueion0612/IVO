from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional
import re

# Import transformers/torch (fallback to simple summarizer if unavailable)
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

    _HAS_TRANSFORMERS = True
except Exception as e:
    print("[WARN] transformers/torch import failed, KoBART summarization disabled.")
    print("       Error:", e)
    _HAS_TRANSFORMERS = False


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
    Simple summarizer that:
    - Splits text by sentence boundaries (.!?...)
    - Keeps only the first N sentences
    """

    def __init__(self, max_sentences: int = 2) -> None:
        self.max_sentences = max_sentences

    def summarize(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""

        # Return as-is if short
        if len(text) < 40:
            return text

        # Simple sentence splitting
        sentences = re.split(r'(?<=[\.!?…])\s+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return text

        return " ".join(sentences[: self.max_sentences])


# ===== KoBART Summarizer (Falls back to Simple Summarizer if unavailable) =====

class KoBartSummarizer:
    """
    Korean text summarizer based on gogamza/kobart-summarization.
    Auto-fallback to SimpleSentenceSummarizer if transformers/torch loading fails.
    """

    def __init__(
        self,
        model_name: str = "gogamza/kobart-summarization",
        device: Optional[str] = None,
        max_input_tokens: int = 512,
        num_beams: int = 4,
        use_model: bool = True,
    ) -> None:
        self.simple = SimpleSentenceSummarizer(max_sentences=2)

        self.enabled = _HAS_TRANSFORMERS and use_model
        self.model = None
        self.tokenizer = None

        if not self.enabled:
            print("[INFO] KoBART disabled: Using SimpleSentenceSummarizer only.")
            return

        try:
            if device is None:
                device = "cuda" if torch.cuda.is_available() else "cpu"

            print(f"[INFO] Loading summarization model... ({model_name}, device={device})")
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
            self.device = device
            self.model.to(device)
            self.model.eval()
            self.max_input_tokens = max_input_tokens
            self.num_beams = num_beams
            print("[INFO] KoBART summarization model loaded.")
        except Exception as e:
            print("[WARN] KoBART loading failed, falling back to SimpleSentenceSummarizer.")
            print("       Error:", e)
            self.enabled = False

    def summarize(self, text: str, max_output_tokens: int = 64) -> str:
        """
        Summarize answer text to 1-2 sentences.
        """
        # Use simple summarizer if model disabled
        if not self.enabled or self.model is None or self.tokenizer is None:
            return self.simple.summarize(text)

        text = text.strip()
        if not text:
            return ""

        # Skip model for very short text
        if len(text) < 40:
            return self.simple.summarize(text)

        try:
            inputs = self.tokenizer(
                [text],
                max_length=self.max_input_tokens,
                truncation=True,
                return_tensors="pt",
            )

            input_ids = inputs["input_ids"].to(self.device)
            attention_mask = inputs["attention_mask"].to(self.device)

            with torch.no_grad():
                output_ids = self.model.generate(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    num_beams=self.num_beams,
                    max_length=max_output_tokens,
                    no_repeat_ngram_size=3,
                    early_stopping=True,
                )

            summary = self.tokenizer.decode(output_ids[0], skip_special_tokens=True)
            summary = summary.strip()
            summary = self._clean_repetition(summary)
            summary = self._first_sentence(summary)
            return summary or self.simple.summarize(text)
        except Exception as e:
            print("[WARN] KoBART summarization error, falling back to SimpleSentenceSummarizer.")
            print("       Error:", e)
            return self.simple.summarize(text)

    @staticmethod
    def _clean_repetition(text: str) -> str:
        """
        Remove consecutive repeated words.
        Example: "summary summary" -> "summary"
        """
        words = text.split()
        cleaned: List[str] = []
        last: Optional[str] = None

        for w in words:
            if w == last:
                continue
            cleaned.append(w)
            last = w

        cleaned_text = " ".join(cleaned)
        cleaned_text = " ".join(cleaned_text.split())
        return cleaned_text

    @staticmethod
    def _first_sentence(text: str) -> str:
        """
        Keep only the first sentence (split by .!?...).
        """
        sentences = re.split(r'(?<=[\.!?…])\s+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return text
        return sentences[0]


# ===== Q/A Summary Pipeline =====

class QASummaryGenerator:
    def __init__(
        self,
        qa_builder: QAPairBuilder,
        summarizer: KoBartSummarizer,
        max_question_chars: int = 120,
        max_answer_tokens: int = 80,
        debug: bool = False,
    ) -> None:
        self.qa_builder = qa_builder
        self.summarizer = summarizer
        self.max_question_chars = max_question_chars
        self.max_answer_tokens = max_answer_tokens
        self.debug = debug

    def _shorten_question(self, q: str) -> str:
        """
        Shorten question:
        - Split into sentences
        - Prefer first sentence ending with '?'
        - Otherwise use first sentence
        """
        q = q.strip()
        if not q:
            return q

        sentences = re.split(r'(?<=[\?\?\.!\!])\s+', q)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return q[: self.max_question_chars]

        # Prefer sentence ending with question mark
        for s in sentences:
            if s.endswith("?") or s.endswith("？"):
                return s

        first = sentences[0]
        if len(first) <= self.max_question_chars:
            return first
        return first[: self.max_question_chars].strip() + " ..."

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
            # Q는 그대로/살짝만 자르기
            q_summary = self._shorten_question(pair.question)

            # A는 요약 모델 통과
            a_summary = self.summarizer.summarize(
                pair.answer,
                max_output_tokens=self.max_answer_tokens,
            )
            if not a_summary:
                a_summary = pair.answer.strip()

            lines.append(f"- Q{i}: {q_summary}")
            lines.append(f"  A{i}: {a_summary}")

        return "\n".join(lines)


# ===== Helper Function for External Use =====

def summarize_qa_bullets(utterances: List[Utterance], debug: bool = False) -> str:
    """
    Summarize STT results (presenter/questioner utterance list) into:
    - Qn: ...
      An: ...
    format string.
    """
    qa_builder = QAPairBuilder()
    summarizer = KoBartSummarizer(device=None, use_model=True)
    qa_summary = QASummaryGenerator(qa_builder, summarizer, debug=debug)
    return qa_summary.summarize_dialogue(utterances)


# ===== Demo with Sample Data =====

if __name__ == "__main__":
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

    print("\n===== Q/A 요약 결과 =====")
    result = summarize_qa_bullets(utterances, debug=True)
    print(result)
    print("================================\n")
