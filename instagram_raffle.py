#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


MENTION_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9._]+)")
MIN_UNIQUE_MENTIONS_TO_PARTICIPATE = 2


@dataclass
class ParticipantStats:
    comments_count: int = 0
    mentions_count: int = 0
    mentioned_usernames: set[str] = field(default_factory=set)


def extract_mentions(text: str) -> list[str]:
    return [match.group(1).lower() for match in MENTION_RE.finditer(text)]


def read_comments_for_raffle(
    input_path: Path, ignore_replies: bool
) -> dict[str, ParticipantStats]:
    participants: dict[str, ParticipantStats] = {}

    with input_path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        required_fields = {"username", "comment", "is_reply"}
        missing_fields = required_fields.difference(reader.fieldnames or [])
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"CSV sem colunas obrigatorias: {missing}")

        for row in reader:
            if ignore_replies and row["is_reply"].strip().lower() == "true":
                continue

            username = row["username"].strip().lower()
            if not username:
                continue

            stats = participants.setdefault(username, ParticipantStats())
            mentions = extract_mentions(row["comment"])
            stats.comments_count += 1
            stats.mentions_count += len(mentions)
            stats.mentioned_usernames.update(mentions)

    return participants


def raffle_rows(participants: dict[str, ParticipantStats]) -> list[dict[str, str | int]]:
    rows = []
    for username, data in participants.items():
        unique_mentions_count = len(data.mentioned_usernames)
        if unique_mentions_count < MIN_UNIQUE_MENTIONS_TO_PARTICIPATE:
            continue

        extra_chances = unique_mentions_count // 2
        total_chances = 1 + extra_chances
        rows.append(
            {
                "username": username,
                "comments_count": data.comments_count,
                "mentions_count": data.mentions_count,
                "unique_mentions_count": unique_mentions_count,
                "extra_chances": extra_chances,
                "total_chances": total_chances,
            }
        )

    return sorted(
        rows,
        key=lambda row: (-int(row["total_chances"]), str(row["username"])),
    )


def export_raffle(
    input_path: Path,
    output_path: Path,
    winners_count: int,
    seed: str | None,
    ignore_replies: bool,
) -> list[str]:
    participants = read_comments_for_raffle(input_path, ignore_replies=ignore_replies)
    rows = raffle_rows(participants)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "username",
                "comments_count",
                "mentions_count",
                "unique_mentions_count",
                "extra_chances",
                "total_chances",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    if winners_count < 1:
        raise ValueError("--winners precisa ser maior que zero.")

    if winners_count > len(rows):
        raise ValueError(
            f"--winners maior que o numero de participantes ({len(rows)})."
        )

    rng = random.Random(seed)
    available_rows = list(rows)
    winners = []
    for _ in range(winners_count):
        winner = rng.choices(
            available_rows,
            weights=[int(row["total_chances"]) for row in available_rows],
            k=1,
        )[0]
        winners.append(str(winner["username"]))
        available_rows.remove(winner)

    return winners


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sorteia participantes a partir de um CSV local de comentarios."
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=Path("comentarios_com_replies.csv"),
        help="CSV de comentarios. Padrao: comentarios_com_replies.csv",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("participantes_sorteio.csv"),
        help="CSV de auditoria com as chances calculadas. Padrao: participantes_sorteio.csv",
    )
    parser.add_argument(
        "-w",
        "--winners",
        type=int,
        default=1,
        help="Quantidade de ganhadores. Padrao: 1",
    )
    parser.add_argument(
        "--seed",
        help="Seed opcional para reproduzir exatamente o mesmo sorteio.",
    )
    parser.add_argument(
        "--ignore-replies",
        action="store_true",
        help="Ignorar respostas no CSV. Por padrao, usa tambem as respostas baixadas.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        winners = export_raffle(
            input_path=args.input,
            output_path=args.output,
            winners_count=args.winners,
            seed=args.seed,
            ignore_replies=args.ignore_replies,
        )
    except FileNotFoundError:
        print(f"Arquivo nao encontrado: {args.input}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"Arquivo de auditoria salvo em {args.output}")
    print("Ganhador(es):")
    for winner in winners:
        print(winner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
