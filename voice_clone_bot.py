#!/usr/bin/env python3
import os
import asyncio
import logging
import tempfile
import shutil
from pathlib import Path
from functools import partial

from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# TTS
from TTS.api import TTS

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "8048394561:AAG3H50kn8QPS9AagjmLRAxSFuOt4BXrh6E")
VOICE_STORE = Path("voices")  # store user voice samples here
OUTPUT_DIR = Path("outputs")
MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"  # example voice-clone-capable model

VOICE_STORE.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(_name_)

# Load TTS model globally (costly). Doing sync because library is sync.
logger.info("Loading TTS model... This can take a while on first run.")
tts = TTS(MODEL_NAME)  # loads model into memory
logger.info("TTS model loaded.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! 👋\nSend /registervoice and attach your voice sample (ogg/mp3/wav). Then use /say <text> to generate speech in your voice."
    )


async def registervoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    # If user sent the command with an attached audio/file
    if msg.reply_to_message and (msg.reply_to_message.voice or msg.reply_to_message.audio or msg.reply_to_message.document):
        attachment = msg.reply_to_message
    else:
        # ask user to reply to a message that contains the voice file
        await msg.reply_text("Please reply to an audio/file message with /registervoice (or send /registervoice while replying to your voice sample).")
        return

    file_msg = msg.reply_to_message
    file = None
    if file_msg.voice:
        file = await file_msg.voice.get_file()
        filename = "voice.ogg"
    elif file_msg.audio:
        file = await file_msg.audio.get_file()
        filename = file_msg.audio.file_name or "voice_audio"
    elif file_msg.document:
        file = await file_msg.document.get_file()
        filename = file_msg.document.file_name or "voice_file"
    else:
        await msg.reply_text("No valid audio found in replied message.")
        return

    user_id = update.effective_user.id
    user_dir = VOICE_STORE / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    # download to temp
    tmp = tempfile.TemporaryDirectory()
    tmp_path = Path(tmp.name) / filename
    await file.download_to_drive(str(tmp_path))

    # convert to wav using ffmpeg (ensures consistent format)
    wav_path = user_dir / "voice_sample.wav"
    conv_cmd = f'ffmpeg -y -i "{tmp_path}" -ar 22050 -ac 1 "{wav_path}"'
    logger.info("Converting file to wav: %s", conv_cmd)
    rc = os.system(conv_cmd)
    if rc != 0 or not wav_path.exists():
        await msg.reply_text("Failed to convert the uploaded audio. Make sure ffmpeg is installed and the file is a valid audio.")
        tmp.cleanup()
        return

    tmp.cleanup()
    await msg.reply_text("✅ Voice sample registered successfully! Now use /say <text> to generate audio in your voice.")


async def say(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = update.effective_user.id
    user_dir = VOICE_STORE / str(user_id)
    sample_wav = user_dir / "voice_sample.wav"
    if not sample_wav.exists():
        await msg.reply_text("No voice sample found. Please register with /registervoice (reply to your voice sample).")
        return

    # text extraction
    if context.args:
        text = " ".join(context.args)
    else:
        # if user sent just text message (no command) we can optionally handle later
        await msg.reply_text("Please use /say <text> with the text you want to convert.")
        return

    await msg.reply_text("Generating audio... (this may take some time on CPU)")

    # create unique output path
    out_wav = OUTPUT_DIR / f"{user_id}_{int(asyncio.get_event_loop().time()*1000)}.wav"
    out_mp3 = out_wav.with_suffix(".mp3")

    # Run TTS (blocking) in threadpool to avoid blocking event loop
    loop = asyncio.get_event_loop()
    run_fn = partial(
        tts.tts_to_file,
        text=text,
        speaker_wav=str(sample_wav),
        file_path=str(out_wav)
    )
    try:
        await loop.run_in_executor(None, run_fn)
    except Exception as e:
        logger.exception("TTS failed")
        await msg.reply_text(f"Failed to generate audio: {e}")
        return

    # convert output to mp3
    conv_cmd = f'ffmpeg -y -i "{out_wav}" -ar 22050 "{out_mp3}"'
    os.system(conv_cmd)
    if not out_mp3.exists():
        await msg.reply_text("Failed to convert generated audio to mp3.")
        return

    # send file
    with open(out_mp3, "rb") as f:
        await msg.reply_audio(audio=InputFile(f, filename=out_mp3.name))

    # cleanup generated files (optional)
    try:
        out_wav.unlink(missing_ok=True)
        out_mp3.unlink(missing_ok=True)
    except Exception:
        pass


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commands:\n/registervoice (reply to your voice file) - register voice sample\n/say <text> - generate speech\n/help - this message"
    )


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("registervoice", registervoice))
    app.add_handler(CommandHandler("say", say))

    # Start the bot
    logger.info("Starting bot...")
    app.run_polling()


if _name_ == "_main_":
    main()
