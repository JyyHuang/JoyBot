import discord
from discord.ext import commands
import asyncio
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

VOICE_CHANNELS = {}
queue = {}
yt_dlp.utils.bug_reports_message = lambda: ""

ytdl_options = {
    "format": "bestaudio/best",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": False,
    "nocheckcertificate": True,
    "ignoreerrors": True,
    "logtostderr": False,
    "quiet": True,
    "extract_flat": "False",
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
}

ffmpeg_options = {
    "options": "-vn",
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
}

ytdl = yt_dlp.YoutubeDL(ytdl_options)


class Commands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.executor = ThreadPoolExecutor(max_workers=5)

    # Event
    # Bot leaves voice channel after 15 minutes if not used
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):

        # Make sure member is bot
        if not member.id == self.bot.user.id:
            return

        # Bot got disconnected
        if after.channel is None:
            text_channel = VOICE_CHANNELS.pop(before.channel.id)
            if text_channel:
                await text_channel.send("Disconnected! :(")

        # if None then that means bot was not in a voice channel before
        # Bot is connected
        elif before.channel is None:
            voice = after.channel.guild.voice_client
            time = 0
            while True:
                await asyncio.sleep(1)
                time += 1
                if voice.is_playing() and not voice.is_paused():
                    time = 0
                if time == 900:
                    await voice.disconnect()
                if not voice.is_connected:
                    break

    # Commands
    # joins channel
    @commands.command(pass_context=True)
    async def join(self, ctx):
        if ctx.author.voice:
            channel = ctx.message.author.voice.channel
            VOICE_CHANNELS[channel.id] = ctx.channel
            if ctx.voice_client is not None:
                return await ctx.voice_client.move_to(channel)
            await channel.connect()
        else:
            await ctx.send("Dush! Please Join a Channel.")

    # leaves channel
    @commands.command(pass_context=True)
    async def leave(self, ctx):
        if ctx.voice_client:
            channel = ctx.guild.voice_client
            await channel.disconnect()
        else:
            await ctx.send("Dush! Please Join a Channel.")

    # play music
    @commands.command(pass_context=True)
    async def play(self, ctx, *, info):

        # check queue function
        async def check_queue(ctx, id):
            try:
                if queue[id]:
                    voice_client = ctx.guild.voice_client
                    source, title = queue[id].pop(0)
                    voice_client.play(
                        source,
                        after=lambda e: asyncio.run_coroutine_threadsafe(
                            check_queue(ctx, ctx.message.guild.id), loop
                        ),
                    )
                    await ctx.send(f"**Now playing:** {title}")
            except Exception as e:
                print(e)

        # checks if user is in voice channel
        # VOICE_CHANNELS is the id of channel where message was sent
        # Dict makes sure bot sends message to that channel only
        try:
            voice_channel = ctx.author.voice.channel
            channel = ctx.message.author.voice.channel
            VOICE_CHANNELS[channel.id] = ctx.channel
            guild_id = ctx.message.guild.id
        except AttributeError:
            return await ctx.send(
                "Dush! Please Join a Channel."
            )  # user is not in a voice channel

        voice_client = ctx.guild.voice_client
        if not voice_client:
            await voice_channel.connect()
            voice_client = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)

        # listens for events
        loop = asyncio.get_event_loop()

        # url
        async def extract_info(info):
            data = await loop.run_in_executor(
                self.executor, lambda: ytdl.extract_info(info, download=False)
            )
            if "entries" in data:
                return data["entries"]
            else:
                return [data]

        async def play_song(ctx, voice_client, guild_id, url, title):

            try:
                source = discord.FFmpegPCMAudio(
                    source=url, **ffmpeg_options, executable="ffmpeg"
                )  # playing the audio
                if voice_client.is_playing():
                    if guild_id in queue:
                        queue[guild_id].append((source, title))
                    else:
                        queue[guild_id] = [(source, title)]
                    if len(queue) >= 1:
                        await ctx.send(f"*{title}* **added to queue**")
                else:
                    voice_client.play(
                        source,
                        after=lambda e: asyncio.run_coroutine_threadsafe(
                            check_queue(ctx, ctx.message.guild.id), loop
                        ),
                    )
                    await ctx.send(f"**Now playing:** *{title}*")

            except Exception as e:
                print(e)

        songs = await extract_info(info)

        tasks = []

        for song in songs:
            if song:

                url = song["url"]
                title = song["title"]

                tasks.append(play_song(ctx, voice_client, guild_id, url, title))

                if len(tasks) >= 20:
                    break
            else:
                await ctx.send("A song is unavailable and will be skipped. Sowwy :/")

        await asyncio.gather(*tasks)

    # pause song
    @commands.command(pass_context=True)
    async def pause(self, ctx):
        try:
            channel = ctx.message.author.voice.channel
            VOICE_CHANNELS[channel.id] = ctx.channel
            playing = ctx.voice_client.is_playing()
            paused = ctx.voice_client.is_paused()
        except AttributeError:
            return await ctx.send("Dush! Please Join a Channel.")
        if paused != True:
            ctx.voice_client.pause()
        else:
            if playing != True:
                ctx.voice_client.resume()

    # stops song and clears queue
    @commands.command(pass_context=True)
    async def stop(self, ctx):
        try:
            channel = ctx.message.author.voice.channel
            VOICE_CHANNELS[channel.id] = ctx.channel
            if ctx.voice_client.is_playing:
                ctx.voice_client.stop()
                queue.clear()
            await ctx.send("Music has stopped")
        except AttributeError:
            return await ctx.send("Dush! Please Join a Channel.")

    # skip
    @commands.command(pass_context=True)
    async def skip(self, ctx):
        try:
            channel = ctx.message.author.voice.channel
            VOICE_CHANNELS[channel.id] = ctx.channel
            if ctx.voice_client.is_playing:
                ctx.voice_client.stop()
        except AttributeError:
            return await ctx.send("Dush! Please Join a Channel.")

    # lists all songs in queue
    @commands.command(pass_context=True)
    async def list(self, ctx):
        counter = 1
        await ctx.send("**IN QUEUE:**")
        for values in queue.values():
            for value in values:
                await ctx.send(f"{counter}. **{value[1]}**")
                counter += 1


async def setup(bot):
    await bot.add_cog(Commands(bot))
