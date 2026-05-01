#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import tempfile
import getpass
from datetime import datetime
from pathlib import Path
from typing import Iterable

try:
    import instaloader
    from instaloader.nodeiterator import NodeIterator
    from instaloader.structures import PostComment, PostCommentAnswer, Profile
except ModuleNotFoundError:
    instaloader = None
    NodeIterator = None
    PostComment = None
    PostCommentAnswer = None
    Profile = None


POST_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|tv)/([^/?#]+)/?"
)
SESSION_PREFIX = "session-"


def extract_shortcode(post_url_or_shortcode: str) -> str:
    value = post_url_or_shortcode.strip()
    match = POST_URL_RE.search(value)
    if match:
        return match.group(1)

    if re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return value

    raise ValueError(
        "Informe uma URL de post/reel do Instagram ou apenas o shortcode."
    )


def session_dirs() -> list[Path]:
    config_home = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    return [
        config_home / "instaloader",
        Path(tempfile.gettempdir()) / f".instaloader-{getpass.getuser()}",
    ]


def find_saved_sessions() -> dict[str, Path]:
    sessions: dict[str, Path] = {}
    for directory in session_dirs():
        if not directory.exists():
            continue

        for session_file in directory.glob(f"{SESSION_PREFIX}*"):
            if session_file.is_file():
                login_name = session_file.name.removeprefix(SESSION_PREFIX)
                sessions[login_name] = session_file

    return sessions


def load_existing_session(loader: instaloader.Instaloader, login: str | None) -> bool:
    sessions = find_saved_sessions()

    if login and login in sessions:
        loader.load_session_from_file(login, str(sessions[login]))
        return True

    if login:
        try:
            loader.load_session_from_file(login)
            return True
        except FileNotFoundError:
            pass

    if len(sessions) == 1:
        session_login, session_file = next(iter(sessions.items()))
        print(
            f"Usando sessao existente {session_file.name!r}.",
            file=sys.stderr,
        )
        loader.load_session_from_file(session_login, str(session_file))
        return True

    if len(sessions) > 1:
        available = ", ".join(sorted(sessions))
        raise RuntimeError(
            f"Mais de uma sessao encontrada ({available}). Use --login com um destes nomes."
        )

    return False


def make_loader(login: str | None, quiet: bool) -> instaloader.Instaloader:
    if instaloader is None:
        raise RuntimeError(
            "Dependencia ausente: instale com `pip install -r requirements.txt`."
        )

    loader = instaloader.Instaloader(
        quiet=quiet,
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
    )

    if load_existing_session(loader, login):
        return loader

    if login:
        print(
            f"Sessao de {login!r} nao encontrada; fazendo login interativo.",
            file=sys.stderr,
        )
        loader.interactive_login(login)
        loader.save_session_to_file()

    return loader


def get_comments_via_graphql(post: instaloader.Post) -> Iterable[PostComment]:
    if NodeIterator is None or PostComment is None or PostCommentAnswer is None or Profile is None:
        raise RuntimeError(
            "Dependencia ausente: instale com `uv sync` ou `uv pip install -r requirements.txt`."
        )

    if not post._context.is_logged_in:
        raise instaloader.LoginRequiredException("Login required to access comments of a post.")

    def post_comment_answer(node):
        return PostCommentAnswer(
            id=int(node["id"]),
            created_at_utc=datetime.utcfromtimestamp(node["created_at"]),
            text=node["text"],
            owner=Profile(post._context, node["owner"]),
            likes_count=node.get("edge_liked_by", {}).get("count", 0),
        )

    def post_comment_answers(node):
        if "edge_threaded_comments" not in node:
            return

        answer_count = node["edge_threaded_comments"]["count"]
        if answer_count == 0:
            return

        answer_edges = node["edge_threaded_comments"]["edges"]
        if answer_count == len(answer_edges):
            yield from (post_comment_answer(comment["node"]) for comment in answer_edges)
            return

        yield from NodeIterator(
            post._context,
            "51fdd02b67508306ad4484ff574a0b62",
            lambda data: data["data"]["comment"]["edge_threaded_comments"],
            post_comment_answer,
            {"comment_id": node["id"]},
            f"https://www.instagram.com/p/{post.shortcode}/",
        )

    def post_comment(node):
        return PostComment(
            context=post._context,
            node=node,
            answers=post_comment_answers(node),
            post=post,
        )

    if post.comments == 0:
        return []

    try:
        comment_edges = post._field("edge_media_to_parent_comment", "edges")
    except KeyError:
        comment_edges = post._field("edge_media_to_comment", "edges")

    answers_count = sum(
        edge["node"].get("edge_threaded_comments", {}).get("count", 0)
        for edge in comment_edges
    )

    if post.comments == len(comment_edges) + answers_count:
        return [post_comment(comment["node"]) for comment in comment_edges]

    return NodeIterator(
        post._context,
        "97b41c52301f77ce508f55e66d17620e",
        lambda data: data["data"]["shortcode_media"]["edge_media_to_parent_comment"],
        post_comment,
        {"shortcode": post.shortcode},
        f"https://www.instagram.com/p/{post.shortcode}/",
    )


def iter_comments(post: instaloader.Post, backend: str) -> Iterable[PostComment]:
    if backend == "graphql":
        yield from get_comments_via_graphql(post)
        return

    if backend == "iphone":
        yield from post._get_comments_via_iphone_endpoint()
        return

    try:
        yield from post.get_comments()
    except instaloader.ConnectionException as exc:
        if "api/v1/media/" not in str(exc) or "/comments/" not in str(exc):
            raise

        print(
            "Endpoint mobile de comentarios falhou; tentando fallback GraphQL.",
            file=sys.stderr,
        )
        yield from get_comments_via_graphql(post)


def comment_rows(
    post: instaloader.Post, include_replies: bool, comments_backend: str
) -> Iterable[dict[str, str | int]]:
    for comment in iter_comments(post, backend=comments_backend):
        yield {
            "comment_id": comment.id,
            "parent_comment_id": "",
            "is_reply": "false",
            "username": comment.owner.username,
            "comment": comment.text,
            "created_at_utc": comment.created_at_utc.isoformat(),
            "likes_count": comment.likes_count,
        }

        if include_replies:
            for answer in comment.answers:
                yield {
                    "comment_id": answer.id,
                    "parent_comment_id": comment.id,
                    "is_reply": "true",
                    "username": answer.owner.username,
                    "comment": answer.text,
                    "created_at_utc": answer.created_at_utc.isoformat(),
                    "likes_count": answer.likes_count,
                }


def export_comments(
    post_url_or_shortcode: str,
    output_path: Path,
    login: str | None,
    include_replies: bool,
    comments_backend: str,
    quiet: bool,
) -> int:
    if instaloader is None:
        raise RuntimeError("Dependencia ausente: instale com `uv sync`.")

    shortcode = extract_shortcode(post_url_or_shortcode)
    loader = make_loader(login=login, quiet=quiet)
    post = instaloader.Post.from_shortcode(loader.context, shortcode)

    fieldnames = [
        "comment_id",
        "parent_comment_id",
        "is_reply",
        "username",
        "comment",
        "created_at_utc",
        "likes_count",
    ]

    count = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for row in comment_rows(
            post,
            include_replies=include_replies,
            comments_backend=comments_backend,
        ):
            writer.writerow(row)
            count += 1

    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exporta usuarios e comentarios de um post/reel do Instagram para CSV."
    )
    parser.add_argument(
        "post",
        help="URL do post/reel ou shortcode, ex: https://www.instagram.com/p/SHORTCODE/",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("comentarios.csv"),
        help="Arquivo CSV de saida. Padrao: comentarios.csv",
    )
    parser.add_argument(
        "-l",
        "--login",
        help=(
            "Email ou usuario do Instagram para carregar sessao do Instaloader. "
            "Se nao houver sessao salva, pede senha no terminal."
        ),
    )
    parser.add_argument(
        "-u",
        "--username",
        dest="username",
        help="Alias antigo para --login. Aceita email ou usuario.",
    )
    parser.add_argument(
        "--include-replies",
        action="store_true",
        help="Incluir respostas a comentarios. Por padrao, exporta apenas comentarios principais.",
    )
    parser.add_argument(
        "--comments-backend",
        choices=["auto", "graphql", "iphone"],
        default="auto",
        help=(
            "Backend para buscar comentarios. Padrao: auto. "
            "Use graphql se o endpoint mobile do Instagram falhar."
        ),
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Reduzir logs do Instaloader.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if instaloader is None:
        print(
            "Dependencia ausente: instale com `uv sync`.",
            file=sys.stderr,
        )
        return 1

    login = args.login or args.username

    try:
        count = export_comments(
            post_url_or_shortcode=args.post,
            output_path=args.output,
            login=login,
            include_replies=args.include_replies,
            comments_backend=args.comments_backend,
            quiet=args.quiet,
        )
    except instaloader.LoginRequiredException:
        print(
            "Instagram exigiu login. Rode com --login SEU_EMAIL ou crie uma sessao com: "
            "uv run instaloader -l SEU_EMAIL",
            file=sys.stderr,
        )
        return 2
    except instaloader.ConnectionException as exc:
        print(f"Erro de conexao/Instagram: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 4
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 5

    print(f"Exportados {count} comentarios para {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
