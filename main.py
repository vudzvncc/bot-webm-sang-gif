import os
import zipfile
import shutil
import asyncio
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands
from discord import app_commands
from moviepy.editor import VideoFileClip

# ==========================================
# 1. WEB SERVER KẾT HỢP FLASK (ĐỂ RENDER ONLINE 24/7)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Bot Discord WebM to GIF is running! 🚀"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ==========================================
# 2. KHỞI TẠO DISCORD BOT
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")  # Lấy Token từ Environment Variables trên Render

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Biến lưu trữ trạng thái người dùng bấm /start
user_waiting_state = {}

def make_progress_bar(percent: int) -> str:
    """Tạo thanh tiến trình emoji"""
    filled_count = int(percent / 10)
    empty_count = 10 - filled_count
    bar = "🟩" * filled_count + "⬜" * empty_count
    return f"{bar} `{percent}%`"

def convert_webm_to_gif(webm_path: str, gif_path: str):
    """
    Chuyển WebM -> MP4 tạm thời -> GIF
    """
    temp_mp4 = webm_path + ".temp.mp4"
    try:
        # Bước 1: WebM -> MP4
        clip = VideoFileClip(webm_path)
        clip.write_videofile(temp_mp4, codec="libx264", audio=False, verbose=False, logger=None)
        clip.close()

        # Bước 2: MP4 -> GIF
        mp4_clip = VideoFileClip(temp_mp4)
        mp4_clip.write_gif(gif_path, verbose=False, logger=None)
        mp4_clip.close()
    finally:
        if os.path.exists(temp_mp4):
            os.remove(temp_mp4)

# ==========================================
# 3. SỰ KIỆN VÀ LỆNH DISCORD
# ==========================================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"🤖 Bot đã sẵn sàng với tên: {bot.user}")

@bot.tree.command(name="start", description="Bắt đầu quy trình chuyển đổi file WebM/ZIP sang GIF")
async def start_command(interaction: discord.Interaction):
    user_waiting_state[interaction.user.id] = True
    await interaction.response.send_message(
        "📥 **[HƯỚNG DẪN]** Vui lòng gửi **01 file `.webm`** hoặc **01 file `.zip`** (chứa các file `.webm`) vào khung chat này để bắt đầu chuyển đổi! 🎬✨",
        ephemeral=False
    )

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Kiểm tra xem người dùng đã dùng lệnh /start chưa
    if user_waiting_state.get(message.author.id):
        if not message.attachments:
            return

        attachment = message.attachments[0]
        filename = attachment.filename.lower()

        # Kiểm tra đuôi file hợp lệ
        if not (filename.endswith(".webm") or filename.endswith(".zip")):
            await message.channel.send("❌ **[LỖI]** Vui lòng gửi file đúng định dạng `.webm` hoặc `.zip`!")
            return

        # Hủy trạng thái chờ sau khi nhận file
        user_waiting_state[message.author.id] = False

        status_msg = await message.channel.send("⏳ **[1/3]** Đang tải file xuống máy chủ...")

        # Thư mục tạm thời xử lý công việc
        work_dir = f"temp_{message.id}"
        os.makedirs(work_dir, exist_ok=True)

        try:
            download_path = os.path.join(work_dir, attachment.filename)
            await attachment.save(download_path)

            webm_files = []

            # Phân loại file `.zip` hay `.webm`
            if filename.endswith(".zip"):
                await status_msg.edit(content="📦 **[2/3]** Đang giải nén và kiểm tra file ZIP...")
                extract_dir = os.path.join(work_dir, "extracted")
                os.makedirs(extract_dir, exist_ok=True)

                with zipfile.ZipFile(download_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)

                # Lấy tất cả file webm (kể cả trong thư mục con, hỗ trợ >65 file)
                for root, _, files in os.walk(extract_dir):
                    for file in files:
                        if file.lower().endswith(".webm"):
                            webm_files.append(os.path.join(root, file))

                if not webm_files:
                    await status_msg.edit(content="❌ **[LỖI]** Không tìm thấy bất kỳ file `.webm` nào bên trong file ZIP của bạn!")
                    shutil.rmtree(work_dir, ignore_errors=True)
                    return
            else:
                webm_files.append(download_path)

            total_files = len(webm_files)
            converted_gifs = []

            # Tiến hành chuyển đổi từng file kèm thanh tiến trình
            for index, webm_path in enumerate(webm_files, start=1):
                percent = int((index / total_files) * 100)
                progress_bar = make_progress_bar(percent)
                
                await status_msg.edit(
                    content=(
                        f"🔄 **[ĐANG CHUYỂN ĐỔI]** ({index}/{total_files} file)\n"
                        f"⚙️ Quy trình: WebM ➔ MP4 ➔ GIF\n"
                        f"{progress_bar}"
                    )
                )

                out_gif_path = os.path.join(work_dir, f"converted_{index}.gif")
                
                # Thực hiện chuyển đổi trong thread riêng để không block bot Discord
                await asyncio.to_thread(convert_webm_to_gif, webm_path, out_gif_path)
                converted_gifs.append(out_gif_path)

            # Đóng gói trả về cho người dùng
            await status_msg.edit(content="📤 **[3/3]** Đang chuẩn bị gửi kết quả...")

            if len(converted_gifs) == 1:
                # Nếu chỉ có 1 file, gửi trực tiếp file GIF
                await message.channel.send(
                    content="🎉 **[HOÀN THÀNH]** File GIF của bạn đây!",
                    file=discord.File(converted_gifs[0], filename="converted.gif")
                )
            else:
                # Nếu nhiều file (>65 file), nén tất cả GIF thành 1 file ZIP rồi gửi
                output_zip_path = os.path.join(work_dir, "all_converted_gifs.zip")
                with zipfile.ZipFile(output_zip_path, 'w') as zip_out:
                    for i, g_path in enumerate(converted_gifs, start=1):
                        zip_out.write(g_path, arcname=f"result_{i}.gif")

                await message.channel.send(
                    content=f"🎉 **[HOÀN THÀNH]** Đã chuyển đổi thành công **{total_files} file WebM** sang GIF!",
                    file=discord.File(output_zip_path, filename="converted_gifs.zip")
                )

            await status_msg.delete()

        except Exception as e:
            await status_msg.edit(content=f"💥 **[XẢY RA LỖI]**: `{str(e)}`")

        finally:
            # Dọn dẹp thư mục tạm sau khi xử lý xong
            if os.path.exists(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)

    await bot.process_commands(message)

# ==========================================
# 4. CHẠY BOT
# ==========================================
if __name__ == "__main__":
    keep_alive()  # Chạy web server Flask
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Chưa cấu hình DISCORD_TOKEN trong Environment Variables!")
