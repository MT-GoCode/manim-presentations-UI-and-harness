from manim import DOWN, LEFT, RIGHT, UP, Circle, FadeIn, FadeOut, ImageMobject, PointCloudDot

from helpers.order import badges


def construct(talk):
    talk.beat("pictures")
    image = ImageMobject(str(talk.root / "assets" / "swatch.png")).scale(3).shift(LEFT * 4 + UP)
    cloud = PointCloudDot(radius=0.4).shift(DOWN * 2)
    backdrop = Circle(1).set_fill(opacity=1).color_using_background_image(str(talk.root / "assets" / "backdrop.png"))
    talk.play(FadeIn(image), FadeIn(cloud), FadeIn(backdrop.shift(RIGHT * 4)))

    talk.beat("ordered")
    talk.play(FadeOut(image, cloud, backdrop))
    talk.play(FadeIn(badges()))
