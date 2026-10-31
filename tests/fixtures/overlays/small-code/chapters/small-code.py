from manim import Code, FadeIn


def construct(talk):
    talk.beat("listing")
    talk.play(FadeIn(Code(code_string="x = 1", language="python", paragraph_config={"font_size": 18})))
