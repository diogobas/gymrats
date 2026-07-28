"""Where the screenshots come from.

The contract is three methods and bytes. These tests are mostly about the two
things that bite: identifiers that travel through a URL and come back as a
path, and screenshots that must survive being processed.
"""

from __future__ import annotations

import pytest
from gymrats.ingestion import (
    IncomingFile,
    LocalFolderSource,
    ScreenshotItem,
    ScreenshotSource,
    UnknownItem,
    UploadSource,
    build_source,
)

PNG = b"\x89PNG\r\n\x1a\n fake"


@pytest.fixture
def inbox(tmp_path):
    return tmp_path / "inbox"


def upload(source: UploadSource, *names: str, **kwargs):
    return source.receive(
        [IncomingFile(name, PNG, "image/png") for name in names], **kwargs
    )


# -- upload ----------------------------------------------------------------


def test_a_batch_is_what_arrived_together(inbox):
    source = UploadSource(inbox)

    batch = upload(source, "IMG_0001.PNG", "IMG_0002.PNG", batch_id="junho")

    assert batch.id == "junho"
    assert [item.filename for item in batch.items] == ["IMG_0001.PNG", "IMG_0002.PNG"]
    assert [item.size for item in batch.items] == [len(PNG), len(PNG)]
    assert source.fetch(batch.items[0]) == PNG


def test_the_identifier_is_ours_not_the_phone_s(inbox):
    """It ends up in a URL and comes back as a path segment.

    So it is built here from a sanitised name, never taken as given.
    """
    source = UploadSource(inbox)

    batch = upload(source, "../../etc/passwd", "foto do rolo.jpeg", batch_id="b")

    assert [item.id for item in batch.items] == ["01-passwd.png", "02-foto-do-rolo.jpeg"]
    assert sorted(path.name for path in (inbox / "b").iterdir()) == [
        "01-passwd.png",
        "02-foto-do-rolo.jpeg",
    ]


def test_a_part_with_no_filename_still_gets_an_extension(inbox):
    """Without one it would be stored and then never recognised as an image."""
    source = UploadSource(inbox)

    batch = source.receive([IncomingFile(None, PNG, "image/png")], batch_id="b")

    assert batch.items[0].id == "01-print.png"
    assert source.list_pending()[0].id == "01-print.png"


def test_climbing_out_of_the_inbox_is_refused(inbox):
    """A forged item is not a missing file, it is an attack.

    Identifiers arrive from a URL. The API only ever fetches items it found in
    ``list_pending``, so this is the second lock, not the first.
    """
    source = UploadSource(inbox)
    upload(source, "a.png", batch_id="b")
    (inbox.parent / "segredo.png").write_bytes(b"nope")

    forged = ScreenshotItem(id="../../segredo.png", batch="b")
    with pytest.raises(UnknownItem):
        source.fetch(forged)
    with pytest.raises(UnknownItem):
        source.fetch(ScreenshotItem(id="a.png", batch=".."))


def test_processed_screenshots_are_moved_and_not_deleted(inbox):
    """A tally that has to be redone needs the images it was made from."""
    source = UploadSource(inbox)
    batch = upload(source, "a.png", "b.png", batch_id="junho")

    source.mark_processed(batch.items[0])

    assert [item.id for item in source.list_pending()] == ["02-b.png"]
    assert (inbox / "junho" / "processed" / "01-a.png").read_bytes() == PNG


def test_pending_spans_every_batch(inbox):
    source = UploadSource(inbox)
    upload(source, "a.png", batch_id="20260601-100000")
    upload(source, "b.png", batch_id="20260702-100000")

    assert [item.batch for item in source.list_pending()] == [
        "20260601-100000",
        "20260702-100000",
    ]


def test_fetching_something_that_is_not_there_says_so(inbox):
    source = UploadSource(inbox)
    upload(source, "a.png", batch_id="b")

    with pytest.raises(UnknownItem):
        source.fetch(ScreenshotItem(id="99-nope.png", batch="b"))


# -- local folder ----------------------------------------------------------


def test_a_folder_of_images_is_a_source(tmp_path):
    (tmp_path / "hustle-1.png").write_bytes(PNG)
    (tmp_path / "hustle-2.png").write_bytes(PNG)
    (tmp_path / "notas.txt").write_text("não é print")

    source = LocalFolderSource(tmp_path)

    assert [item.id for item in source.list_pending()] == ["hustle-1.png", "hustle-2.png"]
    assert source.fetch(source.list_pending()[0]) == PNG


def test_the_local_folder_also_moves_what_it_processed(tmp_path):
    (tmp_path / "a.png").write_bytes(PNG)
    source = LocalFolderSource(tmp_path)

    source.mark_processed(source.list_pending()[0])

    assert source.list_pending() == []
    assert (tmp_path / "processed" / "a.png").is_file()


def test_a_missing_folder_is_simply_empty(tmp_path):
    assert LocalFolderSource(tmp_path / "nope").list_pending() == []


# -- the registry ----------------------------------------------------------


@pytest.mark.parametrize("name", ["upload", "local_folder"])
def test_every_registered_source_satisfies_the_contract(name, tmp_path):
    source = build_source(name, tmp_path)

    assert isinstance(source, ScreenshotSource)
    assert source.list_pending() == []


def test_an_unknown_source_says_which_ones_exist(tmp_path):
    with pytest.raises(ValueError, match="local_folder"):
        build_source("telegram", tmp_path)
