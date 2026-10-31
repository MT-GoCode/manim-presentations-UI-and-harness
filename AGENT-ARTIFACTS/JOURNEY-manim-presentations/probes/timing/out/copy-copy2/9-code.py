from manim import Code, VGroup, config

from .visuals import GPU


class TranscriptCode(VGroup):
    def __init__(self, checkpoint, font_size, position):
        self.checkpoint_id = checkpoint.id
        self.code = Code(
            code_string=checkpoint.code,
            language="python",
            formatter_style="monokai",
            add_line_numbers=False,
            background="rectangle",
            background_config={
                "fill_color": "#000000",
                "stroke_color": GPU,
                "stroke_width": 2,
            },
            paragraph_config={"font_size": font_size},
        ).move_to(position)
        super().__init__(self.code)
        if (
            self.get_left()[0] < -config.frame_width / 2
            or self.get_right()[0] > config.frame_width / 2
            or self.get_bottom()[1] < -config.frame_height / 2
            or self.get_top()[1] > config.frame_height / 2
        ):
            raise ValueError(f"Code panel outside frame: {checkpoint.id}")
