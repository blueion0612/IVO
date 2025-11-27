"""
QA Summarizer Server - JSON protocol based local summarization service
Uses KoBART for Korean text summarization with GPU acceleration

Protocol:
    Input (stdin):  {"command": "summarize", "conversations": [...]}
    Output (stdout): {"type": "ready|summary|error", ...}
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"  # Avoid OMP Error #15 (Windows + CUDA)

import sys
import json
from typing import List, Optional

# Import qa_summarizer module
from qa_summarizer import (
    Utterance,
    QAPairBuilder,
    KoBartSummarizer,
    QASummaryGenerator,
    _HAS_TRANSFORMERS
)


def send_message(msg_type: str, **kwargs):
    """Send JSON message to stdout"""
    msg = {"type": msg_type, **kwargs}
    print(json.dumps(msg, ensure_ascii=False), flush=True)


class QASummarizerServer:
    """JSON protocol based QA Summarizer server for Electron communication"""

    def __init__(self) -> None:
        send_message("info", message="Loading KoBART summarization model...")

        try:
            self.qa_builder = QAPairBuilder()
            self.summarizer = KoBartSummarizer(device=None, use_model=True)
            self.generator = QASummaryGenerator(
                self.qa_builder,
                self.summarizer,
                max_question_chars=120,
                max_answer_tokens=80,
                debug=False
            )
            send_message("ready", model_enabled=self.summarizer.enabled)
        except Exception as e:
            send_message("error", message=f"Failed to load model: {str(e)}")
            raise

    def _convert_conversations(self, conversations: List[dict]) -> List[Utterance]:
        """
        Convert conversation data from renderer to Utterance list

        Input format:
        [
            {"speaker": "presenter", "text": "...", "timestamp": "..."},
            {"speaker": "questioner1", "text": "...", "timestamp": "..."},
            ...
        ]
        """
        utterances = []

        for conv in conversations:
            speaker = conv.get("speaker", "presenter").lower()
            text = conv.get("text", "").strip()

            if not text:
                continue

            # Map speaker names to roles
            # presenter -> presenter
            # questioner1, questioner2, questioner3, q1, q2, q3 -> questioner
            if speaker in ["presenter", "발표자"]:
                role = "presenter"
            elif any(q in speaker for q in ["questioner", "q1", "q2", "q3", "질문자"]):
                role = "questioner"
            else:
                # Default: treat as questioner for Q/A pairing
                role = "questioner"

            utterances.append(Utterance(role=role, text=text))

        return utterances

    def summarize(self, conversations: List[dict]) -> Optional[str]:
        """
        Summarize conversations into Q/A bullet points
        """
        if not conversations:
            send_message("warning", message="No conversations to summarize")
            return None

        try:
            utterances = self._convert_conversations(conversations)

            if not utterances:
                send_message("warning", message="No valid utterances found")
                return None

            # Generate summary
            summary = self.generator.summarize_dialogue(utterances)

            send_message("summary", summary=summary, count=len(conversations))
            return summary

        except Exception as e:
            send_message("error", message=f"Summarization failed: {str(e)}")
            return None

    def run(self):
        """Main loop - reads JSON commands from stdin"""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                cmd = json.loads(line)
                command = cmd.get("command", "")

                if command == "summarize":
                    conversations = cmd.get("conversations", [])
                    self.summarize(conversations)
                elif command == "quit":
                    send_message("shutdown")
                    break
                else:
                    send_message("error", message=f"Unknown command: {command}")

            except json.JSONDecodeError:
                send_message("error", message=f"Invalid JSON: {line}")
            except Exception as e:
                send_message("error", message=f"Command error: {str(e)}")


if __name__ == "__main__":
    try:
        server = QASummarizerServer()
        server.run()
    except Exception as e:
        send_message("error", message=f"Server initialization failed: {str(e)}")
        sys.exit(1)
