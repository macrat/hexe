from typing import Self

import tiktoken


class Tokenizer:
    """LLM tokenizer."""

    __singleton: Self | None = None

    __tokenizer: tiktoken.Encoding

    def __new__(cls, *args, **kwargs) -> "Tokenizer":
        if cls.__singleton is None:
            cls.__singleton = super().__new__(cls)
            cls.__singleton.__tokenizer = tiktoken.get_encoding("cl100k_base")

        return cls.__singleton

    def encode(self, text: str) -> list[int]:
        """Encode text to tokens."""

        return self.__tokenizer.encode(text)

    def count(self, text: str) -> int:
        """Count number of tokens."""

        return len(self.encode(text))
