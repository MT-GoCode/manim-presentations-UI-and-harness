from manim import ClockwiseTransform, FadeTransform, Text, Transform, VGroup


def construct(talk):
    talk.beat("grows")  # the source keeps its small creation size; its declared size is the target's
    small = Text("grow", font_size=16).shift([0, 2, 0])
    talk.add(small)
    talk.play(Transform(small, Text("grow", font_size=48).shift([0, 2, 0])))

    talk.beat("clockwise")
    turn = Text("turn", font_size=16).shift([-3, 0, 0])
    talk.add(turn)
    talk.play(ClockwiseTransform(turn, Text("turn", font_size=40).shift([-3, 0, 0])))

    talk.beat("becomes")
    seed = Text("seed", font_size=12).shift([3, 0, 0])
    talk.add(seed)
    seed.become(Text("tree", font_size=44).shift([3, 0, 0]))
    talk.play(seed.animate.shift([0, -0.5, 0]))

    talk.beat("fades")  # FadeTransform removes the source group: the target's own sizes count
    two = VGroup(Text("a", font_size=40), Text("b", font_size=40)).arrange().shift([0, -2.5, 0])
    talk.add(two)
    three = VGroup(*[Text(c, font_size=36) for c in "xyz"]).arrange().shift([0, -2.5, 0])
    talk.play(FadeTransform(two, three))
