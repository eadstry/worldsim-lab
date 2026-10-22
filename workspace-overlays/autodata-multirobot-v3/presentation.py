"""Make six side-by-side domain comparison videos from the verified HD episodes."""
import argparse, hashlib, json, subprocess
from pathlib import Path
import cv2, imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont
NAMES = {'g1d': '宇树 G1-D', 'openarm': 'OpenArm', 'so101': 'SO101'}
LABELS = ['基准', '暖光', '冷光', '布局与视角', '材质', '背景替换']
p = argparse.ArgumentParser()
p.add_argument('--root', type=Path, required=True)
a = p.parse_args()
out = a.root / 'presentation'
out.mkdir(exist_ok=True)
manifest = []
fontroot = Path('/usr/share/fonts/opentype/noto')
titlefont = ImageFont.truetype(str(fontroot / 'NotoSansCJK-Bold.ttc'), 44, index=2)
labelfont = ImageFont.truetype(str(fontroot / 'NotoSansCJK-Regular.ttc'), 28, index=2)
small = ImageFont.truetype(str(fontroot / 'NotoSansCJK-Regular.ttc'), 20, index=2)
for robot, label in NAMES.items():
    for task in range(2):
        slug = 'pick' if task == 0 else 'sort'
        title = '抓取方块' if task == 0 else 'RGB 方块排序'
        canvas = Image.new('RGB', (1920, 1080), (13, 19, 28))
        draw = ImageDraw.Draw(canvas)
        draw.text((24, 20), f'{label}  |  {title}', font=titlefont, fill=(232, 241, 248))
        draw.text((24, 82), '六种域随机化条件 · 每格为独立验证的物理轨迹', font=small, fill=(143, 174, 192))
        inputs = []
        hashes = []
        frames = []
        positions = []
        for condition, name in enumerate(LABELS):
            col = condition % 3
            row = condition // 3
            x = 24 + col * 632
            y = 156 + row * 460
            positions.append((x, y))
            draw.text((x, y - 44), name, font=labelfont, fill=(145, 211, 225))
            episode = a.root / 'production' / robot / f'episode-{condition * 2 + task:02d}'
            media = json.loads((episode / 'media-verification.json').read_text())
            inputs.append(episode / 'overview.mp4')
            hashes.append(media['sha256'])
            frames.append(media['frames'])
        assert len(set(frames)) == 1
        draw.text((24, 1008), 'WorldSimReady-Home-mini  ·  30 fps  ·  LeRobot v3.0  ·  仿真演示', font=small, fill=(130, 154, 173))
        board = out / f'{robot}-{slug}-board.png'
        canvas.save(board)
        video = out / f'{robot}-{slug}-domain-grid.mp4'
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-nostdin', '-loop', '1', '-framerate', '30', '-i', str(board)]
        for path in inputs:
            cmd.extend(['-i', str(path)])
        filters = ['[0:v]format=yuv420p[base]']
        for index in range(6):
            filters.append(f'[{index + 1}:v]scale=608:342:flags=lanczos,setsar=1[v{index}]')
        for index, (x, y) in enumerate(positions):
            filters.append(f"[{('base' if index == 0 else 'o' + str(index - 1))}][v{index}]overlay={x}:{y}:shortest=1[o{index}]")
        cmd.extend(['-filter_complex', ';'.join(filters), '-map', '[o5]', '-frames:v', str(frames[0]), '-r', '30', '-c:v', 'libx264', '-crf', '16', '-preset', 'fast', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(video)])
        subprocess.run(cmd, check=True)
        cap = cv2.VideoCapture(str(video))
        assert int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) == 1920 and int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) == 1080
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frames[0] * 0.4))
        ok, image = cap.read()
        assert ok
        cv2.imwrite(str(out / f'{robot}-{slug}-domain-grid.png'), image)
        cap.release()
        manifest.append(dict(robot=robot, task=slug, frames=frames[0], source_sha256=hashes, sha256=hashlib.sha256(video.read_bytes()).hexdigest()))
        print('COMPARISON', robot, slug, flush=True)
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
