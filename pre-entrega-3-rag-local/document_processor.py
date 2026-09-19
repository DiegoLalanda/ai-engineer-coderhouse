"""Limpieza y chunking por tokens para documentos de texto."""

from __future__ import annotations

import re

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter


class DocumentProcessor:
    """Preprocesa documentos y crea chunks semánticamente coherentes."""

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        model_encoding: str = "cl100k_base",
    ) -> None:
        if chunk_size < 500:
            raise ValueError("chunk_size debe ser de al menos 500 tokens.")
        if not 0 <= chunk_overlap < chunk_size:
            raise ValueError(
                "chunk_overlap debe ser mayor o igual a 0 y menor que chunk_size."
            )

        self.tokenizer = tiktoken.get_encoding(model_encoding)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=self.calculate_tokens,
            separators=["\n\n", "\n", ". ", ".", " ", ""],
            keep_separator=True,
            strip_whitespace=True,
        )

    def clean_text(self, text: str) -> str:
        """Elimina ruido común sin destruir párrafos ni títulos Markdown."""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\x0c", "\n")
        text = text.replace("\xa0", " ").replace("\u200b", "")

        # Reconstruye palabras cortadas por un salto de línea al extraer un PDF.
        text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)

        # Quita numeración de página aislada: "Página 2", "Page 2 of 8", "2/8".
        text = re.sub(
            r"(?im)^\s*(?:página|page|pág\.?)\s*\d+"
            r"(?:\s*(?:de|of|/)\s*\d+)?\s*$",
            "",
            text,
        )
        text = re.sub(r"(?m)^\s*\d+\s*/\s*\d+\s*$", "", text)
        text = re.sub(r"(?m)^\s*[-–—]?\s*\d+\s*[-–—]?\s*$", "", text)

        # Quita pies y encabezados marcados explícitamente y líneas legales típicas.
        text = re.sub(
            r"(?im)^\s*(?:encabezado|pie de página|header|footer)\s*:?.*$",
            "",
            text,
        )
        text = re.sub(
            r"(?im)^\s*(?:confidencial|confidential|copyright|©|\(c\)).*$",
            "",
            text,
        )

        # Descarta caracteres de reemplazo/control y residuos de tablas mal extraídas.
        text = re.sub(r"[�\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        text = re.sub(r"[|•·]{2,}", " ", text)

        # Normaliza espacios sin eliminar los límites entre párrafos.
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def calculate_tokens(self, text: str) -> int:
        """Calcula la longitud real con el tokenizador configurado."""
        return len(self.tokenizer.encode(text))

    def process_document(self, raw_text: str) -> list[str]:
        """Ejecuta el pipeline de limpieza y fragmentación."""
        cleaned_text = self.clean_text(raw_text)
        if not cleaned_text:
            return []
        return self.splitter.split_text(cleaned_text)
