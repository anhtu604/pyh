from PIL import Image, ImageDraw

from tools.build_mascot_artwork import outline_figure


def test_outline_rings_are_coloured_round_and_deterministic():
    source = Image.new("RGBA", (140, 240))
    ImageDraw.Draw(source).rectangle((40, 20, 99, 219), fill="#18A6A6")
    first = outline_figure(source, "#0A1C2E", "#F7F4EC", inner_width=8, outer_width=4)
    second = outline_figure(source, "#0A1C2E", "#F7F4EC", inner_width=8, outer_width=4)
    assert first.tobytes() == second.tobytes()
    colours = set(first.get_flattened_data())
    assert (10, 28, 46, 255) in colours
    assert (247, 244, 236, 255) in colours
    assert (24, 166, 166, 255) in colours
    assert any(0 < pixel[3] < 255 for pixel in colours)
    # A disk dilation has rounded corners, not a rectangular MaxFilter corner.
    left, top, _right, bottom = first.getbbox()
    assert first.getpixel((left, top))[3] == 0
    mid = (top + bottom) // 2
    assert first.getpixel((left + 2, mid))[:3] == (247, 244, 236)
    assert first.getpixel((left + 7, mid))[:3] == (10, 28, 46)
