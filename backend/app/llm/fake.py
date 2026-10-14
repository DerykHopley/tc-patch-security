"""FakeLLM: the test-only model. No key, no network.

The skeleton only names it; its scripted answers move over from proto with the chat (A06).
"""


class FakeLLM:
    name = "fake"

    def label(self) -> str:
        return "FakeLLM (scripted)"
