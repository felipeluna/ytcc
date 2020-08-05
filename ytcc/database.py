# ytcc - The YouTube channel checker
# Copyright (C) 2019  Wolfgang Popp
#
# This file is part of ytcc.
#
# ytcc is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ytcc is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ytcc.  If not, see <http://www.gnu.org/licenses/>.
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Iterable, Any, NamedTuple, Optional

from ytcc.utils import unpack_optional


class Playlist(NamedTuple):
    name: str
    url: str


class Video(NamedTuple):
    url: str
    title: str
    description: str
    publish_date: datetime
    watched: bool
    duration: float
    extractor_hash: Optional[str] = None


class MappedVideo(Video):
    id: int
    playlists: List[Playlist]


class Database:
    def __init__(self, path: str = ":memory:"):
        is_new_db = True
        if path != ":memory:":
            expanded_path = Path(path).expanduser()
            expanded_path.parent.mkdir(parents=True, exist_ok=True)
            is_new_db = not expanded_path.is_file()
            path = str(expanded_path)

        sqlite3.register_converter("integer", int)
        sqlite3.register_converter("float", float)
        self.connection = sqlite3.connect(f"{path}", detect_types=sqlite3.PARSE_DECLTYPES)
        self.connection.row_factory = sqlite3.Row
        with self.connection as con:
            con.execute("PRAGMA foreign_keys = ON;")

        if is_new_db:
            self._populate()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        self.close()

    def _populate(self):
        script = """CREATE TABLE tag
            (
                name     VARCHAR NOT NULL,
                playlist INTEGER REFERENCES playlist (id) ON DELETE CASCADE,

                CONSTRAINT tagKey PRIMARY KEY (name, playlist)
            );

            CREATE TABLE playlist
            (
                id   INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                name VARCHAR UNIQUE,
                url  VARCHAR UNIQUE
            );

            CREATE TABLE content
            (
                playlist_id INTEGER NOT NULL REFERENCES playlist (id) ON DELETE CASCADE,
                video_id    INTEGER NOT NULL REFERENCES video (id) ON DELETE CASCADE,

                CONSTRAINT contentKey PRIMARY KEY (playlist_id, video_id)
            );

            CREATE TABLE video
            (
                id             INTEGER        NOT NULL PRIMARY KEY AUTOINCREMENT,
                title          VARCHAR        NOT NULL,
                url            VARCHAR UNIQUE NOT NULL,
                description    VARCHAR,
                duration       FLOAT,
                publish_date   FLOAT,
                watched        INTEGER CONSTRAINT watchedBool CHECK (watched = 1 OR watched = 0),
                extractor_hash VARCHAR UNIQUE
            );

            PRAGMA USER_VERSION = 1;
            """
        self.connection.executescript(script)

    def close(self) -> None:
        self.connection.commit()
        self.connection.close()

    def add_playlist(self, name: str, url: str) -> None:
        query = "INSERT INTO playlist (name, url) VALUES (?, ?);"
        self.connection.execute(query, (name, url))

    def delete_playlist(self, name: str) -> None:
        query = "DELETE FROM playlist WHERE name = ?"
        self.connection.execute(query, (name,))

    def rename_playlist(self, oldname, newname) -> None:
        query = "UPDATE OR ROLLBACK playlist SET name = ? WHERE name = ?"
        self.connection.execute(query, (newname, oldname))

    def list_playlists(self) -> Iterable[Playlist]:
        query = "SELECT name, url FROM playlist"
        for row in self.connection.execute(query):
            yield Playlist(row["name"], row["url"])

    def tag(self, playlist: str, tags: List[str]) -> None:
        query_pid = "SELECT id FROM playlist where name = ?"
        query_clear = """DELETE FROM tag where playlist = ?"""
        query_insert = """INSERT OR IGNORE INTO tag VALUES (?, ?)"""
        with self.connection as con:
            pid = int(con.execute(query_pid, (playlist,)).fetchone())
            con.execute(query_clear, (pid,))
            con.executemany(query_insert, ((pid, tag) for tag in tags))

    def add_videos(self, videos: Iterable[Video], playlist: Playlist) -> None:
        insert_video = """
            INSERT OR IGNORE INTO video
            (title, url, description, duration, publish_date, watched, extractor_hash)
            VALUES (:title, :url, :description, :duration, :publish_date, :watched, :extractor_hash);
            """
        insert_playlist = """
            INSERT OR IGNORE INTO content (playlist_id, video_id)
            VALUES (?,?);
            """
        with self.connection as con:
            cursor = con.execute("SELECT id from playlist where name = ?", (playlist.name,))
            playlist_id = cursor.fetchone()["id"]
            for video in videos:
                cursor.execute(insert_video, video._asdict())
                cursor.execute(insert_playlist, (playlist_id, cursor.lastrowid))

    def mark_watched(self, video: MappedVideo) -> None:
        query = "UPDATE video SET watched = 1 where id = ?"
        with self.connection as con:
            con.execute(query, (video.id,))

    def list_videos(self,
                    since: Optional[float] = None,
                    till: Optional[float] = None,
                    watched: Optional[bool] = None,
                    tags: Optional[List[str]] = None,
                    playlists: Optional[List[str]] = None,
                    ids: Optional[List[int]] = None) -> Iterable[MappedVideo]:

        def _placeholder(elements: List[Any]) -> str:
            return ",".join("?" * len(elements))

        tag_condition = f"and t.name in ({_placeholder(tags)})" if tags is not None else ""
        playlist_condition = f"and p.name in ({_placeholder(playlists)})" if playlists is not None else ""
        id_condition = f"and v.id in {_placeholder(ids)}()" if ids is not None else ""
        watched_condition = {None: "", True: "and v.watched", False: "and not v.watched"}.get(watched, "")
        query = f"""
            SELECT v.id             as id,
                   v.title          as title,
                   v.url            as url,
                   v.description    as description,
                   v.duration       as duration,
                   v.publish_date   as publish_date,
                   v.watched        as watched,
                   v.extractor_hash as extractor_hash
            FROM video as v
                     join content c on v.id = c.video_id
                     join playlist p on p.id = c.playlist_id
                     left join tag as t on p.id = t.playlist
            WHERE
                v.publish_date > ?
                and v.publish_date < ?
                {watched_condition}
                {tag_condition}
                {id_condition}
                {playlist_condition}
            """
        since = unpack_optional(since, lambda: 0)
        till = unpack_optional(till, lambda: float("inf"))
        playlists = unpack_optional(playlists, list)
        tags = unpack_optional(tags, list)
        ids = unpack_optional(ids, list)

        with self.connection as con:
            for row in con.execute(query, [since, till] + ids + tags + playlists):
                yield Video(
                    row["url"],
                    row["title"],
                    row["description"],
                    row["publish_date"],
                    row["watched"],
                    row["duration"],
                    row["extractor_hash"]
                )

    def cleanup(self) -> None:
        """Delete all videos from all channels, but keeps the 30 latest videos of every channel."""
        sql = """
            delete
            from video as v
            where (select count(*)
                   from video w
                   where v.publish_date < w.publish_date
                     and v.publisher = w.publisher) >= 30;
            """
        self.connection.commit()
        self.connection.execute(sql)

        # Delete videos without channels.
        # This happend in older versions, because foreign keys were not enabled.
        # Also happens if foreign keys cannot be enabled due to missing compile flags.
        delete_dangling_sql = """
            delete
            from video
            where id in (
              select v.id
              from video v
                     left join channel c on v.publisher = c.yt_channelid
              where c.yt_channelid is null
            );
        """
        self.connection.execute(delete_dangling_sql)

        self.connection.execute("vacuum;")
        self.connection.commit()
