import json
from sms.logger import json_logger as ju

from typing import NamedTuple


import subprocess as sp

import re
import moviepy.editor as mp

from pprint import pprint
from moviepy.tools import subprocess_call
from moviepy.config import get_setting
import os
import cv2
import subprocess
from pathlib import Path
import ffmpeg

from moviepy.editor import VideoFileClip
from PIL import Image
from PIL import ImageDraw

import PIL.ImageFont
import PIL.ImageOps

from sms.file_system_utils import file_system_utils as fsu


# TODO add something like this to check input and MOST IMPORTANTLY output vids:      if file_not_exist_msg(in_vid_path): raise Exception(file_not_exist_msg(in_vid_path)) # Confirm input vid exists

class Impossible_Dims_Exception(Exception): pass


SCRIPT_PARENT_DIR_PATH = os.path.abspath(os.path.dirname(__file__)) # src
TEMP_FRAME_IMGS_DIR_PATH = os.path.join(SCRIPT_PARENT_DIR_PATH, "ignore__temp_frame_imgs")
START_FRAME_IMG_PATH = os.path.join(TEMP_FRAME_IMGS_DIR_PATH, "start_grey_frame_img.jpg")
END_FRAME_IMG_PATH = os.path.join(TEMP_FRAME_IMGS_DIR_PATH, "end_grey_frame_img.jpg")

BLACK_COLOR_RGB = 0


def file_not_exist_msg(file_path):
    if Path(file_path).exists():
        return False
    return f"ERROR: File doesn't exist: {file_path}"

# TODO use? decorator?
def prep_out_path(out_path, out_path_type = "file", prep_mode = "overwrite"):
    if prep_mode == "overwrite":
        fsu.delete_if_exists(out_path)
    else:
        raise NotImplementedError(f"{prep_mode=}")

    if out_path_type == "file":
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    elif out_path_type == "dir":
        Path(out_path).mkdir(parents=True, exist_ok=True)
    else:
        raise ValueError(f"Unrecognized {out_path_type=}")




####################################################################################################
# Get data about given vid
####################################################################################################

def get_vid_dims(vid_file_path):
    vid = cv2.VideoCapture(vid_file_path)
    vid_w_float, vid_h_float = vid.get(cv2.CAP_PROP_FRAME_WIDTH), vid.get(cv2.CAP_PROP_FRAME_HEIGHT)
    return(int(vid_w_float), int(vid_h_float))

def get_vid_length(filename, error_if_vid_not_exist = True, return_type = "sec_float", time_str_sep = "_"):
    ''' return_type = "min_sec_str", "sec_float" '''

    if error_if_vid_not_exist and not Path(filename).is_file():
        raise Exception(f"Error: Vid file does not exist: {filename}")

    result = sp.run(["ffprobe", "-v", "error", "-show_entries",
                    "format=duration", "-of",
                    "default=noprint_wrappers=1:nokey=1", str(Path(filename))],
                    stdout=sp.PIPE,
                    stderr=sp.STDOUT)

    sec_float = float(result.stdout)
    if return_type == "sec_float":
        return sec_float

    min_int, sec_int = divmod(int(sec_float), 60)
    min_int_str_zfill = f"{str(min_int).zfill(2)}"
    sec_int_str_zfill = f"{str(sec_int).zfill(2)}"

    if return_type == "min_sec_str":
        return f"{min_int_str_zfill}{time_str_sep}{sec_int_str_zfill}"

    raise ValueError(f"Invalid {return_type=}")


####################################################################################################
# Vid Time Related
####################################################################################################

def trim_vid(in_vid_path, out_vid_path, time_tup):
    """ Trims vid time from time_tup[0] to time_tup[1]"""
    def ffmpeg_extract_subclip(filename, t1, t2, target_name=None):
        """ Makes a new video file playing video file ``filename`` between
        the times ``t1`` and ``t2``. """
        print('in ffmpeg_extract_subclip')
        name, ext = os.path.splitext(filename)
        if not target_name:
            T1, T2 = [int(1000*t) for t in [t1, t2]]
            target_name = "%sSUB%d_%d.%s" % (name, T1, T2, ext)

        cmd = [get_setting("FFMPEG_BINARY"),"-y",
               "-ss", "%0.2f"%t1,
               "-i", str(Path(filename)),
               "-t", "%0.2f"%(t2-t1),
               "-vcodec", "copy", "-acodec", "copy", str(Path(target_name))]
        subprocess_call(cmd)

    ffmpeg_extract_subclip(in_vid_path, time_tup[0], time_tup[1], target_name=out_vid_path)

    if file_not_exist_msg(out_vid_path): raise FileNotFoundError(file_not_exist_msg(out_vid_path)) # Raise Error if output not created
    return out_vid_path

####################################################################################################
# Resize Vid
####################################################################################################

# TODO look into better quality? ffmpeg -i input.mp4 -vf scale=1280:720 -preset slow -crf 18 output.mp4    https://ottverse.com/change-resolution-resize-scale-video-using-ffmpeg/
def scale_vid(new_vid_dim_tup, in_vid_path, out_vid_path):
    """
        new_vid_dims = w x h
        Example - ffmpeg -i video.mov -vf "scale=250:150" new_movie.mp4
        Will reduce H by 1 if not even
    """
    # Create out_vid_path if not exist
    out_vid_parent_dir_path_obj = Path(out_vid_path).parent
    out_vid_parent_dir_path_obj.mkdir(parents=True,exist_ok=True)

    # Delete out_vid_path if exists
    fsu.delete_if_exists(out_vid_path)

    w = new_vid_dim_tup[0]
    h = new_vid_dim_tup[1]

    # otherwise will get error:  ffmpeg height not divisible by 2
    if h % 2 != 0:
        h = h - 1

    cmd = f'ffmpeg -i {in_vid_path} -vf "scale={w}:{h}" {out_vid_path}'
    print(f"Running: {cmd}...")
    sp.call(cmd, shell = True)

    if file_not_exist_msg(out_vid_path): raise FileNotFoundError(file_not_exist_msg(out_vid_path)) # Raise Error if output not created
    return out_vid_path

####################################################################################################
# Crop vid
####################################################################################################

def crop_vid(w, h, x, y, in_vid_path, out_vid_path):
    """
        w: Width of the output video (out_w). It defaults to iw. This expression is evaluated only once during the filter configuration.
        h: Height of the output video (out_h). It defaults to ih. This expression is evaluated only once during the filter configuration.
        x: Horizontal position, in the input video, of the left edge of the output video. It defaults to (in_w-out_w)/2. This expression is evaluated per-frame.
        y: Vertical position, in the input video, of the top edge of the output video. It defaults to (in_h-out_h)/2. This expression is evaluated per-frame.

        https://www.bogotobogo.com/FFMpeg/ffmpeg_cropping_video_image.php
    """

    fsu.delete_if_exists(out_vid_path)

    cmd = f'ffmpeg -i {in_vid_path} -vf "crop={w}:{h}:{x}:{y}" {out_vid_path}'
    print(f"Running: {cmd}...")
    sp.call(cmd, shell = True)

    if file_not_exist_msg(out_vid_path): raise FileNotFoundError(file_not_exist_msg(out_vid_path)) # Raise Error if output not created


def crop_black_border_from_vid_if_needed(in_vid_path, out_vid_path):
    fsu.delete_if_exists(out_vid_path)
    Path(out_vid_path).parent.mkdir(parents=True, exist_ok=True)

    cropdetect_output = sp.run(['ffmpeg', '-hide_banner', '-i', str(Path(in_vid_path)), '-vf', 'cropdetect', '-t', '1', '-f', 'null', 'pipe:'], stdout=sp.PIPE, stderr=sp.STDOUT, universal_newlines=True).stdout

    # print(f"{cropdetect_output=}")
    # # print(f"{cropdetect_output.=}")
    # line_l = []
    # for line in cropdetect_output.split("\n"):
    #     line_l.append(line)
    # pprint(line_l)
    # print("========================================================================")
    # print("========================================================================")
    # print("========================================================================")
    # print("========================================================================")

    # Return: crop=480:304:72:4
    crop_str = re.search('crop=.*', cropdetect_output).group(0)  # Find the first match of "crop=", and return all characters from "crop=" up to new line.

    # ffmpeg -hide_banner -i in_vid_path -vf crop=480:304:72:4,setsar=1 out_vid_path
    # Can fail with msg like "Invalid too big or non positive size for width '-1264' or height '-704'"
    # - If this happens, will not throw exception, but will make out_vid_path w/ 0 bytes
    # - This fail happens almost immediately, no significant time lost
    # - Therefore, just return in_vid_path if no new vid created
    # sp.run(['ffmpeg', '-hide_banner', '-i', f'"{in_vid_path}"', '-vf', crop_str+',setsar=1', f'"{out_vid_path}"'])
    sp.run(['ffmpeg', '-hide_banner', '-i', str(Path(in_vid_path)), '-vf', crop_str+',setsar=1', str(Path(out_vid_path))])

    if not Path(out_vid_path).is_file():
        raise FileNotFoundError(f"File does not exist, not sure what could cause this: {out_vid_path=}")

    # just return in_vid_path if no new vid created
    if os.path.getsize(out_vid_path) == 0:
        fsu.delete_if_exists(out_vid_path)
        return in_vid_path
    else:
        return out_vid_path


def crop_sides_of_vid_to_match_aspect_ratio(vid_dim_tup_to_match_aspect_ratio, in_vid_path, out_vid_path):
    """
        Makes in_vid match given aspect ratio by only cropping the sides of video
        Good for trimming sides of MC Parkour vids while keeping center
    """
    in_vid_dim_tup = get_vid_dims(in_vid_path)
    in_vid_w = in_vid_dim_tup[0]
    in_vid_h = in_vid_dim_tup[1]
    print(f"    {in_vid_w=}")
    print(f"    {in_vid_h=}")

    aspect_ratio = vid_dim_tup_to_match_aspect_ratio[0] / vid_dim_tup_to_match_aspect_ratio[1]

    new_vid_w = int(in_vid_h * aspect_ratio) # TMP NOT SURE IF ADDING INT BREAKS SOMETHING
    print(f"    new vid dims {new_vid_w} x {in_vid_h}")

    if new_vid_w > in_vid_w:
        raise Impossible_Dims_Exception(f"ERROR: {new_vid_w=} > {in_vid_w=}, This means it's impossible to make \
{in_vid_path=} which has W={in_vid_w} & H={in_vid_h} match \
{vid_dim_tup_to_match_aspect_ratio=} by only cropping sides of in_vid.  To make the aspect \
ratios match, would need to either need to increase width of in_vid (by adding black bars \
or by stretching) or by cropping height of in_vid, which is out of the scope of this function")

    # At this point, h should be the same, only w has changed (reduced)
    w_diff = in_vid_w - new_vid_w

    if w_diff % 2:
        w_diff = w_diff - 1

    num_pixels_to_trim_from_both_sides = int(w_diff / 2)
    # print(f"----------------")

    # print(f"{in_vid_w=}")
    # print(f"{new_vid_w=}")
    # print(f"{w_diff=}")
    # print(f"----------------")


    # crop_vid(w = w_diff,
    crop_vid(w = new_vid_w,
             h = in_vid_h,
             x = num_pixels_to_trim_from_both_sides,
             y = 0,
             in_vid_path = in_vid_path, out_vid_path = out_vid_path)

    print(f"    ----------------")
    print(f"    {vid_dim_tup_to_match_aspect_ratio=}")
    print(f"    {in_vid_dim_tup=}")
    print(f"    {in_vid_w=}")
    print(f"    {new_vid_w=}")
    print(f"    {w_diff=}")
    print(f"    ----------------")

    print(f"    {in_vid_dim_tup=}")
    print(f"    {aspect_ratio=}")
    print(f"    {new_vid_w=}")
    print(f"    {w_diff=}")
    print(f"    {num_pixels_to_trim_from_both_sides=}")
    # exit()
    return out_vid_path

def crop_sides_of_vid_by_percent(trim_percent, in_vid_path, out_vid_path):
    """
        Crops trim_percent of total width of in_vid from the sides evenly, leaving the video centered
        - Good for trimming non-important sides of shows like Family Guy
        - If trim_percent == 0 - Will return in_vid_path
        - trim_percent =  10, 20, 30, etc.
        - EXAMPLE:
            If in_vid.size == (100, 44) pixels and trim_percent == 10:
                out_vid.size will = (90, 44) pixels, created from cropping 5 pixels from each side of in_vid
    """
    print(f"in crop_sides_of_vid_by_percent() - {trim_percent=}")

    if trim_percent == 0:
        print(f"Told to trim sides of video by 0%, so just returning {in_vid_path=} and deleting {out_vid_path=} if exists to remove confusion...")
        fsu.delete_if_exists(out_vid_path)
        return in_vid_path

    in_vid_dim_tup = get_vid_dims(in_vid_path)
    in_vid_w = in_vid_dim_tup[0]
    in_vid_h = in_vid_dim_tup[1]

    num_pixels_wide_to_remove_total = int(in_vid_w * (trim_percent / 100))
    num_pixels_wide_to_keep_total = in_vid_w - num_pixels_wide_to_remove_total
    num_pixels_to_trim_from_both_sides = int(num_pixels_wide_to_remove_total / 2)

    print(f"{num_pixels_wide_to_remove_total=}")
    print(f"{num_pixels_wide_to_keep_total=}")
    print(f"{num_pixels_to_trim_from_both_sides=}")
    print(f"{in_vid_dim_tup=}")

    crop_vid(w = num_pixels_wide_to_keep_total,
                h = in_vid_h,
                x = num_pixels_to_trim_from_both_sides,
                y = 0,
                in_vid_path = in_vid_path, out_vid_path = out_vid_path)

    print(f"{(trim_percent / 100)=}")
    print(f"{num_pixels_wide_to_remove_total=}")
    print(f"{num_pixels_to_trim_from_both_sides * 2=}")
    print(f"{in_vid_w - (num_pixels_to_trim_from_both_sides * 2)=}")
    print(f"{num_pixels_wide_to_keep_total=}")
    print(f"{num_pixels_to_trim_from_both_sides=}")
    print(f"{in_vid_dim_tup=}")
    # exit()
    return out_vid_path

####################################################################################################
# Combine multiple vids into new vid
####################################################################################################

def stack_vids(top_vid_path, bottom_vid_path, out_vid_path):
    top_vid_dim_tup = get_vid_dims(top_vid_path)
    top_vid_w = top_vid_dim_tup[0]
    bottom_vid_dim_tup = get_vid_dims(bottom_vid_path)
    print(f"{bottom_vid_dim_tup=}")
    bottom_vid_w = bottom_vid_dim_tup[0]

    if top_vid_w != bottom_vid_w:
        raise Exception(f"Widths of vids not the same, behavior for this not implemented - {top_vid_dim_tup=} , {bottom_vid_dim_tup=}")

    fsu.delete_if_exists(out_vid_path)
    Path(out_vid_path).parent.mkdir(parents=True, exist_ok=True)


    # This command does the following:
    #     ffmpeg is the command to run ffmpeg.
    #     -i top_video.mp4 specifies the input file for the top video.
    #     -i bottom_video.mp4 specifies the input file for the bottom video.
    #     -filter_complex "[0:v][1:v]vstack=inputs=2[v]" specifies a filter complex that takes the video streams from
    #                                                    both input files ([0:v] and [1:v]) and stacks them vertically
    #                                                    to create a new video stream ([v]).
    #     -map "[v]" tells ffmpeg to use the stacked video stream as the output video.
    #     -map 0:a tells ffmpeg to use the audio stream from the top video (0:a) as the output audio.
    #     -c:v libx264 specifies the codec to use for the output video.
    #     -crf 18 specifies the quality level for the output video. A lower value results in a higher quality video,
    #             but a larger file size.
    #     -preset veryfast specifies the speed/quality tradeoff for the output video. A faster preset will result in a
    #                      faster encoding time, but potentially lower quality.
    #     output.mp4 specifies the output file for the combined video.
    # Note that this command assumes that both input videos have the same length. If the videos have different lengths,
    # you may need to specify an additional filter to pad one of the videos to match the length of the other. You can
    # also adjust the parameters (e.g. codec, quality, etc.) to suit your needs.
    cmd = f'ffmpeg \
        -i {top_vid_path} \
        -i {bottom_vid_path} \
        -filter_complex "[0:v][1:v]vstack=inputs=2[v]" \
        -map "[v]" \
        -map 0:a \
        -c:v libx264 \
        -crf 18 \
        -preset veryfast \
        {out_vid_path}'

    print(f"Running: {cmd}...")
    sp.call(cmd, shell = True)

    if file_not_exist_msg(out_vid_path): raise FileNotFoundError(file_not_exist_msg(out_vid_path)) # Raise Error if output not created
    return out_vid_path


def embed_sub_file_into_vid_file(sub_file_path, in_vid_path, out_vid_path):
    ''' // TMP might not work at all '''
    video = ffmpeg.input(in_vid_path)
    audio = video.audio
    ffmpeg.concat(video.filter("subtitles", os.path.abspath(sub_file_path)), audio, v=1, a=1).output(out_vid_path).run()
    if file_not_exist_msg(out_vid_path): raise FileNotFoundError(file_not_exist_msg(out_vid_path)) # Raise Error if output not created

def burn_subs_into_vid(sub_file_path, in_vid_path, out_vid_path):
    cmd = f"ffmpeg -i {in_vid_path} -vf subtitles={sub_file_path} {out_vid_path}"
    print(f"Running {cmd}...")
    sp.call(cmd, shell=True)
    if file_not_exist_msg(out_vid_path): raise FileNotFoundError(file_not_exist_msg(out_vid_path)) # Raise Error if output not created


# TODO move to subtitle utils?
def convert_subs(in_sub_path, out_sub_path):
    cmd = f'tt convert -i "{in_sub_path}" -o "{out_sub_path}"'
    print(f"Running {cmd}...")
    sp.call(cmd, shell=True)
    if file_not_exist_msg(out_sub_path): raise FileNotFoundError(file_not_exist_msg(out_sub_path)) # Raise Error if output not created


def extract_embedded_subs_from_vid_to_separate_file(vid_path, new_sub_file_path):
    cmd = f'ffmpeg -i {vid_path} -map 0:s:0 {new_sub_file_path}'
    print(f"Running {cmd}...")
    sp.call(cmd, shell=True)
    if file_not_exist_msg(new_sub_file_path): raise FileNotFoundError(file_not_exist_msg(new_sub_file_path)) # Raise Error if output not created


def convert_vid_to_diff_format__no_subs(in_vid_path, out_vid_path):
    """ Can use to convert .mp4 to .mkv """
    fsu.delete_if_exists(out_vid_path)
    Path(out_vid_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = f'ffmpeg -i "{in_vid_path}" -c copy -c:s copy "{out_vid_path}"'
    print(f"Running {cmd}...")
    sp.call(cmd, shell=True)
    if file_not_exist_msg(out_vid_path): raise FileNotFoundError(file_not_exist_msg(out_vid_path)) # Raise Error if output not created


def convert_to_mp4(mkv_file): # TODO remove?
    name, ext = os.path.splitext(mkv_file)
    out_name = name + ".mp4"
    ffmpeg.input(mkv_file).output(out_name).run()
    print("Finished converting {}".format(mkv_file))


# def convert_vid_to_diff_format__w_subs(in_vid_path, out_vid_path):
#     """ Can use to convert .mp4 to .mkv """
#     fsu.delete_if_exists(out_vid_path)
#     Path(out_vid_path).parent.mkdir(parents=True, exist_ok=True)

#     # cmd = f'ffmpeg -i {in_mp4_path} -i {in_sub_path} -c copy -c:s mov_text {out_mkv_path}'
#     cmd = f'ffmpeg -i {in_vid_path} -c copy -c:s "C:/p/tik_tb_vid_big_data/ignore/BIG_BOY_fg_TBS/YT_PL_DATA/Family_Guy__Muppets__Clip____TBS/f2_Family.Guy.S05E11.The.Tan.Aquatic.with.Steve.Zissou.REALLY.REAL.DVDRIp.XviD-FAMiLYGuY.eng.srt" {out_vid_path}'
#     print(f"Running {cmd}...")
#     sp.call(cmd, shell=True)

def combine_mp4_and_sub_into_mkv(in_mp4_path, in_sub_path, out_mkv_path):
    """ sub may need to be .srt """
    cmd = f'ffmpeg -i {in_mp4_path} -i {in_sub_path} -c copy -c:s copy {out_mkv_path}'
    print(f"Running {cmd}...")
    sp.call(cmd, shell=True)
    if file_not_exist_msg(out_mkv_path): raise FileNotFoundError(file_not_exist_msg(out_mkv_path)) # Raise Error if output not created



class FFProbeResult(NamedTuple):
    return_code: int
    json: str
    error: str


def _ffprobe(file_path) -> FFProbeResult:
    command_array = ["ffprobe",
                     "-v", "quiet",
                     "-print_format", "json",
                     "-show_format",
                     "-show_streams",
                     file_path]
    result = subprocess.run(command_array, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    return FFProbeResult(return_code=result.returncode,
                         json=result.stdout,
                         error=result.stderr)

def ffprobe_to_d(in_vid_path):
    # fsu.delete_if_exists(out_json_path)
    # Path(out_json_path).parent.mkdir(parents=True, exist_ok=True)

    ffprobe_result = _ffprobe(in_vid_path)
    if ffprobe_result.return_code == 0:
        # # Print the raw json string
        # print(ffprobe_result.json)

        # or print a summary of each stream
        d = json.loads(ffprobe_result.json)
        return d
    else:
        raise ValueError(f"Return code does not equal 0: {ffprobe_result.return_code=}")

def ffprobe_to_json(in_vid_path, out_json_path):
    # fsu.delete_if_exists(out_json_path)
    # Path(out_json_path).parent.mkdir(parents=True, exist_ok=True)
    ffprobe_result_d = ffprobe_to_d(in_vid_path)
    ju.write(ffprobe_result_d, out_json_path)



if __name__ == "__main__":
    # import make_tb_vid
    # make_tb_vid.make_tb_vid()

    # import batch_make_tb_vids
    # batch_make_tb_vids.main()

    combine_mp4_and_sub_into_mkv(in_mp4_path = "C:/tmp/embed_mp4/Family_Guy__Back_To_The_Pilot__Clip____TBS/Family_Guy__Back_To_The_Pilot__Clip____TBS.mp4",
     in_sub_path = "C:/tmp/embed_mp4/Family_Guy__Back_To_The_Pilot__Clip____TBS/Family_Guy__Back_To_The_Pilot__Clip____TBS.en-orig.srt",
      out_mkv_path = "C:/tmp/embed_mp4/Family_Guy__Back_To_The_Pilot__Clip____TBS/o.mp4")



    # d = ffprobe_to_d("C:/tmp/S05E11__Family_Guy__Muppets__Clip____TBS.mkv")
    # pprint(d)
    # ffprobe_to_json("C:/tmp/S05E11__Family_Guy__Muppets__Clip____TBS.mkv", "C:/tmp/ffprobe_test/S05E11__Family_Guy__Muppets__Clip____TBS__ffprobe.json")

    # scale_vid(new_vid_dim_tup = (1440,1080),
    #  in_vid_path = "C:/tmp/S05E11__Family_Guy__Muppets__Clip____TBS.mkv",
    #   out_vid_path = "C:/tmp/S05E11__Family_Guy__Muppets__Clip____TBS__SCALED.mkv")

    # convert_to_mp4("C:/tmp/S06E12__Family_Guy__Pirate_Talk__Clip____TBS.mkv")
    # convert_vid_to_diff_format__no_subs("C:/p/tik_tb_vid_big_data/ignore/BIG_BOY_fg_TBS/man_edit_big_clips/S06E12__Family_Guy__Pirate_Talk__Clip____TBS (1).mkv",
    # "C:/tmp/pirate_no_subs.mp4")
    # # convert_vid_to_diff_format__no_subs("C:/tmp/S05E11__Family_Guy__Muppets__Clip____TBS__SCALED.mkv",
    # # convert_vid_to_diff_format__no_subs("C:/tmp/S05E11__Family_Guy__Muppets__Clip____TBS.mkv",
    # convert_vid_to_diff_format__w_subs("C:/tmp/S05E11__Family_Guy__Muppets__Clip____TBS.mkv",
    # "C:/tmp/S05E11__Family_Guy__Muppets__Clip____TBS__SCALED.ts")

    # combine_mp4_and_sub_into_mkv("C:/tmp/S05E11__Family_Guy__Muppets__Clip____TBS.mkv",
    # "C:/p/tik_tb_vid_big_data/ignore/BIG_BOY_fg_TBS/YT_PL_DATA/Family_Guy__Muppets__Clip____TBS/f2_Family.Guy.S05E11.The.Tan.Aquatic.with.Steve.Zissou.REALLY.REAL.DVDRIp.XviD-FAMiLYGuY.eng.srt",
    # "C:/tmp/S05E11__Family_Guy__Muppets__Clip____TBS.ts")

    # print("start")
    # # burn_subs_into_vid(sub_file_path = "C:/Users/Brandon/Documents/Personal_Projects/tik_tb_vid_big_data/ignore/test/sub_embed_test/og_clip.ttml",
    # #                              in_vid_path = "C:/Users/Brandon/Documents/Personal_Projects/tik_tb_vid_big_data/ignore/test/sub_embed_test/og_clip.mp4",
    # #                              out_vid_path = "C:/Users/Brandon/Documents/Personal_Projects/tik_tb_vid_big_data/ignore/test/sub_embed_test/embed_clip.mp4")

    # # extract_embedded_subs_from_vid_to_separate_file("C:/Users/Brandon/Documents/Personal_Projects/youtube_utils/ignore/embed_subs_pl_test/Inventions_that_Backfire/Invention_that_backfires_2/Invention_that_backfires_2.mp4",
    # # "C:/Users/Brandon/Documents/Personal_Projects/youtube_utils/ignore/embed_subs_pl_test/Inventions_that_Backfire/Invention_that_backfires_2/Invention_that_backfires_2.srt")

    # # combine_mp4_and_sub_into_mkv(in_mp4_path="C:/Users/Brandon/Documents/Personal_Projects/youtube_utils/ignore/Family_Guy__Blue_Harvest_(Clip)___TBS/Family_Guy__Blue_Harvest_(Clip)___TBS.mp4",
    # #  in_sub_path = "C:/Users/Brandon/Documents/Personal_Projects/youtube_utils/ignore/Family_Guy__Blue_Harvest_(Clip)___TBS/Family_Guy__Blue_Harvest_(Clip)___TBS.en.srt",
    # #  out_mkv_path="C:/Users/Brandon/Documents/Personal_Projects/youtube_utils/ignore/Family_Guy__Blue_Harvest_(Clip)___TBS/Family_Guy__Blue_Harvest_(Clip)___TBS_combined.mkv")

    # convert_vid_to_diff_format__no_subs(in_vid_path = "C:/Users/Brandon/Documents/Other/temp/Family_Guy__McStroke__Clip____TBS.mp4",
    #  out_vid_path = "C:/Users/Brandon/Documents/Other/temp/Family_Guy__McStroke__Clip____TBS.mkv")


    # print("done")

    # # tt convert -i "C:/Users/Brandon/Documents/Personal_Projects/tik_tb_vid_big_data/ignore/test/sub_embed_test/og_clip.ttml" -o "C:/Users/Brandon/Documents/Personal_Projects/tik_tb_vid_big_data/ignore/test/sub_embed_test/og_clip.srt"
