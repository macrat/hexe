import time
import uuid
from dataclasses import dataclass
from datetime import datetime

import chromadb
from chromadb.utils import embedding_functions

from tokenizer import Tokenizer


@dataclass
class Note:
    """A note that is stored in the database."""

    id: uuid.UUID | None
    _content: str
    created_at: datetime
    expires_at: datetime
    _n_tokens: int
    distance: float | None

    def __init__(
        self,
        content: str,
        created_at: datetime,
        expires_at: datetime,
        id: uuid.UUID | None = None,
        n_tokens: int | None = None,
        distance: float | None = None,
    ) -> None:
        self.id = id
        self._content = content
        self.created_at = created_at
        self.expires_at = expires_at

        if n_tokens is not None:
            self._n_tokens = n_tokens
        else:
            self._n_tokens = Tokenizer().count(content)

        self.distance = distance

    @property
    def n_tokens(self) -> int:
        return self._n_tokens

    @property
    def content(self) -> str:
        return self._content

    @content.setter
    def content(self, value: str) -> None:
        self._content = value
        self._n_tokens = Tokenizer().count(value)


class NoteDB:
    """Database for storing notes."""

    def __init__(self, path: str, namespace: uuid.UUID) -> None:
        """Initialize the database.

        :param path: Path to the database.
        :param namespace: Namespace for generating UUID of notes.
        """

        self.__ns = namespace

        db = chromadb.PersistentClient(path)
        # ef = embedding_functions.OpenAIEmbeddingFunction(
        #    api_key=os.environ["OPENAI_API_KEY"],
        #    model_name="text-embedding-ada-002",
        # )
        self.__collection = db.get_or_create_collection(
            str(namespace),
            # embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

    def save(self, user_id: str, notes: list[Note]) -> None:
        """Save notes to the database.

        :param user_id: ID of the user who owns the notes.
        :param notes: List of notes to save.
        """

        user_ns = uuid.uuid5(self.__ns, user_id)
        ids = [str(uuid.uuid5(user_ns, x.content)) for x in notes]

        exists = self.__collection.get(ids=ids)
        notes = [note for note, id_ in zip(notes, ids) if id_ not in exists["ids"]]
        ids = [id_ for id_ in ids if id_ not in exists["ids"]]

        if len(notes) == 0:
            return

        self.__collection.add(
            documents=[x.content for x in notes],
            metadatas=[
                {
                    "user_id": user_id,
                    "created_at": x.created_at.timestamp(),
                    "expires_at": x.expires_at.timestamp(),
                    "n_tokens": Tokenizer().count(x.content),
                }
                for x in notes
            ],
            ids=ids,
        )

    def delete(self, user_id: str, ids: list[uuid.UUID]) -> None:
        """Delete notes from the database.

        :param user_id: ID of the user who owns the notes.
        :param ids: List of IDs of notes to delete.
        """

        self.__collection.delete(
            ids=[str(id) for id in ids],
            where={"user_id": user_id},
        )

    def query(
        self, user_id: str, query: str, n_results: int = 10, threshold: float = 0.15
    ) -> list[Note]:
        """Search notes from the database.

        :param user_id: ID of the user who owns the notes.
        :param query: Query string.
        :param n_results: Maximum number of results to return.
        :param threshold: Threshold of similarity.
        """

        result = self.__collection.query(
            where={
                "$and": [
                    {"user_id": user_id},
                    {"expires_at": {"$gt": time.time()}},  # type: ignore
                ],
            },
            query_texts=[query],
            n_results=n_results,
        )

        if (
            result["ids"] is None
            or result["documents"] is None
            or result["metadatas"] is None
            or result["distances"] is None
        ):
            return []

        return [
            Note(
                id=uuid.UUID(id),
                content=content,
                created_at=datetime.fromtimestamp(float(metadata["created_at"])),
                expires_at=datetime.fromtimestamp(float(metadata["expires_at"])),
                n_tokens=int(metadata["n_tokens"]),
                distance=distance,
            )
            for id, content, metadata, distance in zip(
                result["ids"][0],
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
            )
            if distance <= threshold
        ]
