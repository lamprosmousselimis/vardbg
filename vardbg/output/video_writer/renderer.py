import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import Config
from .gif_encoder import GIFEncoder
from .opencv_encoder import OpenCVEncoder
from .webp_encoder import WebPEncoder

WATERMARK = "Generated by vardbg"


class FrameRenderer:
    RED = 0
    GREEN = 1
    BLUE = 2

    def __init__(self, path, config_path):
        # Config
        self.cfg = Config(config_path)
        # Video encoder
        ext = Path(path).suffix.lower()[1:]
        if ext == "mp4":
            self.encoder = OpenCVEncoder(path, "mp4v", self.cfg.fps, self.cfg.w, self.cfg.h)
        elif ext == "gif":
            self.encoder = GIFEncoder(path, self.cfg.fps)
        elif ext == "webp":
            self.encoder = WebPEncoder(path, self.cfg.fps)
        else:
            raise ValueError(f"Unrecognized file extension '{ext}'")
        # Drawing context
        self.draw = None
        # Fonts
        self.body_font = ImageFont.truetype(*self.cfg.font_body)
        self.body_bold_font = ImageFont.truetype(*self.cfg.font_body_bold)
        self.caption_font = ImageFont.truetype(*self.cfg.font_caption)
        self.head_font = ImageFont.truetype(*self.cfg.font_heading)
        self.intro_font = ImageFont.truetype(*self.cfg.font_intro)

        # Sizes and positions to be calculated later
        self.sizes_populated = False
        # Code body size
        self.line_height = None
        self.body_cols = None
        self.body_rows = None
        # Output body start position
        self.out_x = None
        self.out_y = None
        # Output body size
        self.out_cols = None
        self.out_rows = None
        # Variable body start positions
        self.vars_x = None
        self.vars_y = None
        self.ovars_x = None
        self.ovars_y = None
        # Variable body size
        self.vars_cols = None
        self.vars_rows = None
        self.ovars_cols = None
        self.ovars_rows = None

        # Per-frame positions
        self.last_var_x = None
        self.last_var_y = None
        self.ref_var_x = None
        self.ref_var_y = None

        # Current video frame (image)
        self.frame = None

        # Write intro (if necessary)
        if self.cfg.intro_text and self.cfg.intro_time:
            self.write_intro()

    def calc_sizes(self):
        # Calculate text sizes
        w, h = self.draw.textsize("A", font=self.body_font)
        hw, hh = self.draw.textsize("A", font=self.head_font)

        # Code body size
        self.line_height = h * self.cfg.line_height
        self.body_cols = (self.cfg.var_x - self.cfg.sect_padding * 2) // w
        self.body_rows = ((self.cfg.out_y - self.cfg.sect_padding * 2) / self.line_height) - 1

        # Output body start position
        self.out_x = self.cfg.sect_padding
        self.out_y = self.cfg.out_y + self.cfg.head_padding * 2 + hh - self.line_height

        # Output body size
        self.out_cols = self.body_cols
        self.out_rows = int((self.cfg.h - self.out_y) / self.line_height)

        # Variable body start positions
        # Top-left X and Y for last variable section
        self.vars_x = self.cfg.var_x + self.cfg.sect_padding
        self.vars_y = self.cfg.head_padding * 2 + hh

        # Columns and rows for last variable section
        self.vars_cols = (self.cfg.w - self.cfg.var_x - self.cfg.sect_padding * 2) // w
        self.vars_rows = int(((self.cfg.ovar_y - self.cfg.sect_padding * 2) / self.line_height) - 1)

        # Top-left X and Y for other variables section
        self.ovars_x = self.vars_x
        self.ovars_y = self.cfg.ovar_y + self.vars_y - self.line_height

        # Columns and rows for other variables section
        self.ovars_cols = self.vars_cols
        ovars_h = self.cfg.h - self.cfg.ovar_y
        self.ovars_rows = int(((ovars_h - self.cfg.sect_padding * 2) / self.line_height) - 1)

    def get_color(self, col):
        if col == self.RED:
            return self.cfg.red
        elif col == self.GREEN:
            return self.cfg.green
        else:
            return self.cfg.blue

    def draw_text_center(self, x, y, text, font, color):
        w, h = self.draw.textsize(text, font=font)
        self.draw.text((x - w / 2, y - h / 2), text, font=font, fill=color)

    def new_frame(self):
        # Create image
        self.frame = Image.new("RGB", (self.cfg.w, self.cfg.h), self.cfg.bg)
        # Create drawing context
        self.draw = ImageDraw.Draw(self.frame)

    def start_frame(self):
        self.new_frame()

        # Draw output section
        # Horizontal divider at 4/5 height
        self.draw.line(((0, self.cfg.out_y), (self.cfg.var_x, self.cfg.out_y)), fill=self.cfg.fg_body, width=1)
        # Label horizontally centered and padded
        out_center_x = self.cfg.var_x / 2
        out_y = self.cfg.out_y + self.cfg.head_padding
        self.draw_text_center(
            out_center_x, out_y, "Output", self.head_font, self.cfg.fg_heading,
        )

        # Draw variable section
        # Vertical divider at 2/3 width
        self.draw.line(((self.cfg.var_x, 0), (self.cfg.var_x, self.cfg.h)), fill=self.cfg.fg_body, width=1)
        # Label horizontally centered in the variable section and vertically padded
        var_center_x = self.cfg.var_x + ((self.cfg.w - self.cfg.var_x) / 2)
        self.draw_text_center(var_center_x, self.cfg.head_padding, "Last Variable", self.head_font, self.cfg.fg_heading)

        # Draw other variables section
        # Horizontal divider at 1/3 height
        self.draw.line(
            ((self.cfg.var_x, self.cfg.ovar_y), (self.cfg.w, self.cfg.ovar_y)), fill=self.cfg.fg_body, width=1
        )
        # Label similar to the first, but in the others section instead
        ovar_label_y = self.cfg.ovar_y + self.cfg.head_padding
        self.draw_text_center(var_center_x, ovar_label_y, "Other Variables", self.head_font, self.cfg.fg_heading)

        if not self.sizes_populated:
            self.calc_sizes()
            self.sizes_populated = True

    def finish_frame(self, var_state):
        # Bail out if there's no frame to finish
        if self.frame is None:
            return

        # Draw variable state (if available)
        if var_state is not None:
            self.draw_variables(var_state)

        if self.cfg.watermark:
            self.draw_watermark()

        self.encoder.write(self.frame)

    def write_intro(self):
        frames = round(self.cfg.intro_time / self.cfg.fps)
        for _ in range(frames):
            self.new_frame()
            x = self.cfg.w / 2
            y = self.cfg.h / 2
            self.draw_text_center(x, y, self.cfg.intro_text, self.intro_font, self.cfg.fg_heading)
            self.finish_frame(None)

    def draw_code(self, lines, cur_line):
        cur_idx = cur_line - 1

        # Construct list of (line, highlighted) tuples
        unwrapped_lines = [(line, i == cur_idx) for i, line in enumerate(lines)]

        # Wrap lines while preserving highlighted status
        wrapped_lines = []
        for line, highlighted in unwrapped_lines:
            line_wrapped = textwrap.wrap(line, width=self.body_cols)
            if len(line_wrapped) == 0:
                # Empty lines still count
                wrapped_lines.append(("", highlighted))
            else:
                for line_seg in line_wrapped:
                    wrapped_lines.append((line_seg, highlighted))

        # Calculate start and end display indexes with an equivalent number of lines on both sides for context
        ctx_side_lines = self.body_rows / 2 - 1
        start_idx = round(cur_idx - ctx_side_lines)
        end_idx = round(cur_idx + ctx_side_lines)
        # Accommodate for situations where not enough lines are available at the beginning
        if start_idx < 0:
            start_extra = abs(start_idx)
            end_idx += start_extra
            start_idx = 0
        end_idx += 1
        # Slice selected section
        display_lines = wrapped_lines[start_idx:end_idx]

        # Render processed lines
        for i, (line, highlighted) in enumerate(display_lines):
            # Calculate line coordinates
            x = self.cfg.sect_padding
            y_top = self.cfg.sect_padding + self.line_height * (i + 1)
            y_bottom = y_top - self.line_height

            # Draw highlight background if necessary
            if highlighted:
                x_max = self.cfg.var_x - self.cfg.sect_padding
                self.draw.rectangle(((x, y_top), (x_max, y_bottom)), fill=self.cfg.highlight)

            # Draw text
            self.draw.text((x, y_bottom), line, fill=self.cfg.fg_body, font=self.body_font)

    def draw_output(self, lines):
        lines = lines[-self.out_rows :]
        self.draw_text_block(lines, self.out_x, self.out_y)

    def draw_exec(self, nr_times, cur, avg, total):
        x = self.cfg.sect_padding
        # Padding + body
        y = self.cfg.sect_padding + self.line_height * self.body_rows

        plural = "" if nr_times == 1 else "s"
        text = f"Line executed {nr_times} time{plural} — current time elapsed: {cur}, average: {avg}, total: {total}"
        self.draw.text((x, y), text, font=self.caption_font)

    def draw_text_block(self, lines, x_top, y_left):
        for i, line in enumerate(lines):
            # Calculate line coordinates
            x = x_top
            y_top = y_left + self.line_height * (i + 1)
            y_bottom = y_top - self.line_height

            self.draw.text((x, y_bottom), line, fill=self.cfg.fg_body, font=self.body_font)

    def draw_last_var(self, state):
        # Draw variable name
        nw, nh = self.draw.textsize(state.name + " ", font=self.body_font)
        self.draw.text((self.vars_x, self.vars_y - nh), state.name + " ", fill=self.cfg.fg_body, font=self.body_font)
        # Draw action with color
        self.draw.text((self.vars_x + nw, self.vars_y - nh), state.action, fill=state.color, font=self.body_bold_font)

        # Draw remaining text
        self.draw_text_block(state.text_lines, self.vars_x, self.vars_y)

        # Save final action position for relationship drawing (if necessary)
        if state.ref is not None:
            aw, ah = self.draw.textsize(state.action + " ", font=self.body_bold_font)
            self.last_var_x = self.vars_x + nw + aw
            self.last_var_y = self.vars_y - nh / 2

    def draw_other_vars(self, state):
        # Draw text
        self.draw_text_block(state.other_text_lines, self.ovars_x, self.ovars_y)

        # Save referenced variable position for relationship drawing (if necessary)
        if state.ref is not None:
            # Find index of the referenced line
            ref_idx = None
            line = None
            for i, line in enumerate(state.other_text_lines):
                if line == state.ref + ":":
                    ref_idx = i
                    break
            if ref_idx is None:
                return

            # Calculate target reference position
            rw, _ = self.draw.textsize(line + " ", font=self.body_font)
            self.ref_var_x = self.ovars_x + rw
            self.ref_var_y = self.ovars_y + self.line_height * (ref_idx + 1) - self.line_height / 2

    def draw_var_ref(self, state):
        # Calculate X position to route the line on
        # It should be as short as possible while not obscuring any variables or exceeding the scene width
        right_line_x = min(
            max(self.last_var_x, self.ref_var_x) + self.cfg.sect_padding, self.cfg.w - self.cfg.sect_padding / 2
        )

        # Draw the polyline
        self.draw.line(
            (
                (self.last_var_x, self.last_var_y),
                (right_line_x, self.last_var_y),
                (right_line_x, self.ref_var_y),
                (self.ref_var_x, self.ref_var_y),
            ),
            fill=state.color,
            width=2,
        )

    def draw_variables(self, state):
        self.draw_other_vars(state)
        self.draw_last_var(state)

        if state.ref is not None:
            self.draw_var_ref(state)

    def draw_watermark(self):
        # Get target bottom-right position
        x = self.cfg.w - self.cfg.sect_padding
        y = self.cfg.h - self.cfg.sect_padding

        # Subtract text size to position it properly
        w, h = self.draw.textsize(WATERMARK, font=self.caption_font)
        x -= w
        y -= h

        # Draw text
        self.draw.text((x, y), WATERMARK, fill=self.cfg.fg_watermark, font=self.caption_font)

    def close(self, var_state):
        # Finish final frame
        self.finish_frame(var_state)
        # Close encoder
        self.encoder.stop()
