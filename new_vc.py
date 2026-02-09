import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import os
import ssl
from typing import Optional

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

import aiohttp
from aiohttp.connector import TCPConnector

original_init = TCPConnector.__init__

def new_init(self, *args, **kwargs):
    kwargs['ssl'] = ssl_context
    return original_init(self, *args, **kwargs)

TCPConnector.__init__ = new_init


class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        
        super().__init__(command_prefix='!', intents=intents)
        self.server_id = 944823319885152296 # your server id here
        self.commands_channel_id = 1449616094707974154 # your channel id here (same goes in bottom)
        
        self.commands_synced = False
        
        self.queues = {}
        self.loop_states = {}
        self.now_playing = {}
        
        self.ytdl_format_options = {
            'format': 'bestaudio/best',
            'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
            'restrictfilenames': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'quiet': True,
            'no_warnings': True,
            'default_search': 'auto',
            'age_limit': 25,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls'],
                    'player_client': ['android', 'web']
                }
            },
        }

        self.ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -probesize 25M -analyzeduration 25M',
            'options': '-vn -b:a 128k -ac 2'
        }

        self.ytdl = yt_dlp.YoutubeDL(self.ytdl_format_options)
        self.voice_channel_check_task = None
        self.command_sync_task = None

    def get_queue(self, guild_id):
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]
    
    def get_loop_state(self, guild_id):
        if guild_id not in self.loop_states:
            self.loop_states[guild_id] = False
        return self.loop_states[guild_id]
    
    def set_loop_state(self, guild_id, state):
        self.loop_states[guild_id] = state

    def get_now_playing(self, guild_id):
        return self.now_playing.get(guild_id)
    
    def set_now_playing(self, guild_id, song_data):
        self.now_playing[guild_id] = song_data

    async def setup_hook(self):
        print("Running setup hook...")
        
        self.voice_channel_check_task = self.loop.create_task(self.monitor_voice_channels())
        
        self.command_sync_task = self.loop.create_task(self.periodic_command_sync())
        
        await self.sync_commands()

    async def periodic_command_sync(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await asyncio.sleep(1800)
                
                if self.is_ready() and not self.commands_synced:
                    print("Periodic command sync check...")
                    await self.sync_commands()
            except Exception as e:
                print(f"Error in periodic_command_sync: {e}")
                await asyncio.sleep(300)

    async def sync_commands(self):
        try:
            guild = discord.Object(id=self.server_id)
            
            self.tree.copy_global_to(guild=guild)
            
            synced = await self.tree.sync(guild=guild)
            self.commands_synced = True
            
            print(f"✅ Slash commands synced successfully! {len(synced)} commands available.")
            
            await asyncio.sleep(2)
            guild_commands = await self.tree.fetch_commands(guild=guild)
            print(f"✅ Verified {len(guild_commands)} commands available in guild.")
            
        except discord.errors.HTTPException as e:
            print(f"⚠️ HTTP error syncing commands: {e}")
            self.commands_synced = False
        except Exception as e:
            print(f"⚠️ Error syncing commands: {e}")
            self.commands_synced = False
            await asyncio.sleep(60)
            await self.sync_commands()

    async def monitor_voice_channels(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                for voice_client in self.voice_clients:
                    if voice_client.is_connected():
                        members_in_vc = [member for member in voice_client.channel.members if not member.bot]
                        
                        if len(members_in_vc) == 0:
                            await asyncio.sleep(60)
                            
                            members_in_vc_after = [member for member in voice_client.channel.members if not member.bot]
                            if (voice_client.is_connected() and len(members_in_vc_after) == 0):
                                commands_channel = self.get_channel(self.commands_channel_id)
                                if commands_channel:
                                    embed = discord.Embed(
                                        title="Voice Channel Left",
                                        description="Left voice channel due to no one being in VC for 1 minute",
                                        color=0xFFFFFF
                                    )
                                    await commands_channel.send(embed=embed)
                                guild_id = voice_client.guild.id
                                if guild_id in self.queues:
                                    self.queues[guild_id].clear()
                                if guild_id in self.loop_states:
                                    self.loop_states[guild_id] = False
                                if guild_id in self.now_playing:
                                    del self.now_playing[guild_id]
                                # Stop and disconnect
                                if voice_client.is_playing():
                                    voice_client.stop()
                                await asyncio.sleep(1)
                                await voice_client.disconnect()
            except Exception as e:
                print(f"Error in monitor_voice_channels: {e}")
            await asyncio.sleep(10)

    async def safe_voice_connect(self, voice_channel):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return await self.connect_and_deafen(voice_channel)
            except discord.errors.ConnectionClosed as e:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1 * (attempt + 1))
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1 * (attempt + 1))

    async def connect_and_deafen(self, voice_channel):
        try:
            if voice_channel.guild.voice_client:
                await voice_channel.guild.voice_client.disconnect()
                await asyncio.sleep(0.5)
            
            voice_client = await asyncio.wait_for(
                voice_channel.connect(timeout=10.0, reconnect=False), 
                timeout=15.0
            )
            
            # Deafen the bot
            await voice_client.guild.change_voice_state(channel=voice_channel, self_deaf=True)
            
            await asyncio.sleep(1)
            
            return voice_client
            
        except asyncio.TimeoutError:
            raise Exception("Connection timeout - please try again")
        except Exception as e:
            print(f"Voice connection error: {e}")
            raise

    async def cleanup_voice_client(self, guild_id):
        guild = self.get_guild(guild_id)
        if guild and guild.voice_client:
            try:
                if guild.voice_client.is_playing():
                    guild.voice_client.stop()
                await guild.voice_client.disconnect()
            except:
                pass
            await asyncio.sleep(0.5)

    async def play_next(self, guild_id, voice_client):
        try:
            queue = self.get_queue(guild_id)
            loop_state = self.get_loop_state(guild_id)
            
            if loop_state and self.get_now_playing(guild_id):
                current_song = self.get_now_playing(guild_id)
                await self.play_song(guild_id, voice_client, current_song)
                return
            
            if queue:
                song_data = queue.pop(0)
                await self.play_song(guild_id, voice_client, song_data)
            else:
                self.set_loop_state(guild_id, False)
                self.set_now_playing(guild_id, None)
        except Exception as e:
            print(f"Error in play_next: {e}")

    async def play_song(self, guild_id, voice_client, song_data):
        try:
            audio_url = await self.get_audio_url(song_data['url'])
            
            if not audio_url:
                print("Failed to get audio URL")
                await self.play_next(guild_id, voice_client)
                return
            
            audio_source = discord.FFmpegPCMAudio(
                audio_url,
                **self.ffmpeg_options,
                stderr=asyncio.subprocess.DEVNULL
            )
            
            # Add volume control
            audio_source = discord.PCMVolumeTransformer(audio_source, volume=0.5)
            
            def after_playing(error):
                if error:
                    print(f'Player error: {error}')
                coro = self.play_next(guild_id, voice_client)
                asyncio.run_coroutine_threadsafe(coro, self.loop)
            
            if voice_client.is_playing():
                voice_client.stop()
                await asyncio.sleep(0.5)
            
            voice_client.play(audio_source, after=after_playing)
            self.set_now_playing(guild_id, song_data)
            
            channel = self.get_channel(song_data['request_channel_id'])
            if channel:
                embed = discord.Embed(
                    title="🎵 Now Playing",
                    description=f"**{song_data['title']}**",
                    color=0xFFFFFF
                )
                if song_data.get('duration'):
                    duration = song_data['duration']
                    embed.add_field(name="Duration", value=f"{duration//60}:{duration%60:02d}", inline=True)
                if song_data.get('uploader'):
                    embed.add_field(name="Uploader", value=song_data['uploader'], inline=True)
                
                if self.get_loop_state(guild_id):
                    embed.add_field(name="Loop", value="🔁 Enabled", inline=True)
                
                embed.set_footer(text=f"Requested by {song_data['requester_name']}")
                await channel.send(embed=embed)
                
        except Exception as e:
            print(f"Error playing song: {e}")
            await self.play_next(guild_id, voice_client)

    async def get_audio_url(self, url):
        try:
            loop = asyncio.get_event_loop()
            
            try:
                data = await loop.run_in_executor(None, lambda: self.ytdl.extract_info(url, download=False))
            except yt_dlp.utils.ExtractorError as e:
                print(f"Extraction failed: {e}. Trying alternative method...")
                temp_options = self.ytdl_format_options.copy()
                temp_options['extractor_args'] = {
                    'youtube': {
                        'skip': ['dash', 'hls'],
                        'player_client': ['ios', 'android_embedo']
                    }
                }
                temp_ytdl = yt_dlp.YoutubeDL(temp_options)
                data = await loop.run_in_executor(None, lambda: temp_ytdl.extract_info(url, download=False))
            
            if 'entries' in data:
                data = data['entries'][0]
            
            if 'url' in data:
                return data['url']
            else:
                for format in data.get('formats', []):
                    if format.get('acodec') != 'none' and format.get('vcodec') == 'none':
                        return format['url']
                
                for format in data.get('formats', []):
                    if format.get('url'):
                        return format['url']
                        
        except Exception as e:
            print(f"Error getting audio URL: {e}")
            if "age" in str(e).lower() or "sign in" in str(e).lower():
                print("This video is age-restricted. Bot cannot play age-restricted content without YouTube cookies.")
        
        return None

bot = MusicBot()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} guild(s)')
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening, 
            name="ZapBot | /play"
        )
    )
    
    if not bot.commands_synced:
        print("Commands not synced, attempting to sync now...")
        await bot.sync_commands()

@bot.event
async def on_resumed():
    print("Bot has resumed connection")
    await bot.sync_commands()

@bot.event
async def on_guild_available(guild):
    if guild.id == bot.server_id:
        print(f"Guild {guild.name} is now available")
        await bot.sync_commands()

@bot.event
async def on_voice_state_update(member, before, after):
    if member == bot.user:
        if before.channel and after.channel and before.channel != after.channel:
            print(f"Bot moved from {before.channel.name} to {after.channel.name}")
    
    # Handle when bot gets disconnected
    if member == bot.user and before.channel and not after.channel:
        print("Bot was disconnected from voice channel")
        guild_id = before.channel.guild.id
        if guild_id in bot.queues:
            bot.queues[guild_id].clear()
        if guild_id in bot.loop_states:
            bot.loop_states[guild_id] = False
        if guild_id in bot.now_playing:
            del bot.now_playing[guild_id]

@bot.tree.command(name="play", description="Play a song from YouTube")
@app_commands.describe(query="Song name or YouTube URL")
async def play_slash(interaction: discord.Interaction, query: str):
    if not interaction.user.voice:
        embed = discord.Embed(
            title="Error",
            description="You need to be in a voice channel to play music!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await interaction.response.defer()
    
    try:
        # Extract video info
        loop = asyncio.get_event_loop()
        search_data = await loop.run_in_executor(None, lambda: bot.ytdl.extract_info(f"ytsearch5:{query}", download=False))
        
        search_results = search_data.get('entries', []) if 'entries' in search_data else [search_data]
        
        if not search_results:
            embed = discord.Embed(
                title="No Results Found",
                description="No videos found for your search query.",
                color=0xFFFFFF
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        description = ""
        for i, result in enumerate(search_results[:5], 1):
            title = result.get('title', 'Unknown Title')
            duration = result.get('duration')
            duration_str = f" ({duration//60}:{duration%60:02d})" if duration else ""
            description += f"{i}. {title}{duration_str}\n"
        
        embed = discord.Embed(
            title="Search Results",
            description=description,
            color=0xFFFFFF
        )
        embed.set_footer(text="The first result will be played automatically")
        await interaction.followup.send(embed=embed)
        
        first_result = search_results[0]
        
        song_data = {
            'url': first_result.get('webpage_url', first_result.get('original_url', query)),
            'title': first_result.get('title', 'Unknown Title'),
            'duration': first_result.get('duration'),
            'uploader': first_result.get('uploader', 'Unknown'),
            'requester_name': interaction.user.display_name,
            'request_channel_id': interaction.channel.id
        }
        
        if first_result.get('age_limit', 0) > 18:
            embed = discord.Embed(
                title="⚠️ Age-Restricted Content",
                description="This video is age-restricted and cannot be played by the bot.",
                color=0xFFA500
            )
            embed.add_field(name="Video", value=first_result.get('title', 'Unknown'))
            embed.add_field(name="Alternative", value="Try searching for a different video")
            await interaction.followup.send(embed=embed)
            return
        
        voice_client = interaction.guild.voice_client
        
        if not voice_client or not voice_client.is_connected():
            voice_client = await bot.safe_voice_connect(interaction.user.voice.channel)
        elif voice_client.channel != interaction.user.voice.channel:
            if voice_client.is_playing():
                voice_client.stop()
            await voice_client.disconnect()
            await asyncio.sleep(0.5)
            voice_client = await bot.safe_voice_connect(interaction.user.voice.channel)
        
        queue = bot.get_queue(interaction.guild.id)
        queue.append(song_data)
        
        if not voice_client.is_playing() and not voice_client.is_paused():
            await bot.play_next(interaction.guild.id, voice_client)
        else:
            embed = discord.Embed(
                title="🎵 Added to Queue",
                description=f"**{song_data['title']}**\nPosition in queue: {len(queue)}",
                color=0xFFFFFF
            )
            await interaction.followup.send(embed=embed)
        
    except Exception as e:
        print(f"Play command error: {e}")
        error_msg = str(e)
        
        if "age" in error_msg.lower() or "sign in" in error_msg.lower():
            embed = discord.Embed(
                title="⚠️ Age-Restricted Content",
                description="This video requires age verification and cannot be played.",
                color=0xFFA500
            )
            embed.add_field(name="Error", value="YouTube age-restricted content detected")
            embed.add_field(name="Solution", value="Try searching for a different video or version")
        else:
            embed = discord.Embed(
                title="Connection Error",
                description="Failed to connect to voice channel. Please try again.",
                color=0xFFFFFF
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        await bot.cleanup_voice_client(interaction.guild.id)

@bot.tree.command(name="queue", description="Show the current music queue")
async def queue_slash(interaction: discord.Interaction):
    queue = bot.get_queue(interaction.guild.id)
    loop_state = bot.get_loop_state(interaction.guild.id)
    now_playing = bot.get_now_playing(interaction.guild.id)
    
    embed = discord.Embed(title="🎵 Music Queue", color=0xFFFFFF)
    
    if now_playing:
        embed.add_field(
            name="Now Playing",
            value=f"**{now_playing['title']}**\n👤 {now_playing['requester_name']}",
            inline=False
        )
    
    if queue:
        description = ""
        for i, song in enumerate(queue[:10], 1):
            duration = f" ({song['duration']//60}:{song['duration']%60:02d})" if song.get('duration') else ""
            description += f"**{i}. {song['title']}**{duration}\n"
            description += f"   👤 {song['requester_name']}\n\n"
        
        if len(queue) > 10:
            description += f"... and {len(queue) - 10} more songs"
        
        embed.add_field(name="Up Next", value=description, inline=False)
    else:
        embed.add_field(
            name="Queue",
            value="No songs in queue. Use `/play` to add some!",
            inline=False
        )
    
    loop_status = "🔁 **Enabled**" if loop_state else "➡️ **Disabled**"
    embed.add_field(name="Loop Mode", value=loop_status, inline=True)
    embed.add_field(name="Total Songs", value=str(len(queue)), inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="loop", description="Toggle loop for the current song")
async def loop_slash(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_connected():
        embed = discord.Embed(
            title="Error",
            description="I'm not connected to a voice channel!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if not voice_client.is_playing() and not voice_client.is_paused():
        embed = discord.Embed(
            title="Error",
            description="No audio is currently playing!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    current_loop = bot.get_loop_state(interaction.guild.id)
    new_loop_state = not current_loop
    bot.set_loop_state(interaction.guild.id, new_loop_state)
    
    if new_loop_state:
        embed = discord.Embed(
            title="🔁 Loop Enabled",
            description="Current song will now loop continuously",
            color=0xFFFFFF
        )
    else:
        embed = discord.Embed(
            title="➡️ Loop Disabled",
            description="Loop has been turned off",
            color=0xFFFFFF
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pause", description="Pause the current song")
async def pause_slash(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_connected():
        embed = discord.Embed(
            title="Error",
            description="I'm not connected to a voice channel!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if voice_client.is_playing():
        voice_client.pause()
        embed = discord.Embed(
            title="⏸️ Paused",
            description="The current song has been paused",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(
            title="Error",
            description="No audio is currently playing!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="resume", description="Resume the paused song")
async def resume_slash(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_connected():
        embed = discord.Embed(
            title="Error",
            description="I'm not connected to a voice channel!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if voice_client.is_paused():
        voice_client.resume()
        embed = discord.Embed(
            title="▶️ Resumed",
            description="The song has been resumed",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(
            title="Error",
            description="Audio is not paused!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="skip", description="Skip the current song")
async def skip_slash(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_connected():
        embed = discord.Embed(
            title="Error",
            description="I'm not connected to a voice channel!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
        embed = discord.Embed(
            title="⏭️ Skipped",
            description=f"The song has been skipped by {interaction.user.mention}",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(
            title="Error",
            description="No audio is currently playing!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="stop", description="Stop the music and clear the queue")
async def stop_slash(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_connected():
        embed = discord.Embed(
            title="Error",
            description="I'm not connected to a voice channel!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
    
    guild_id = interaction.guild.id
    if guild_id in bot.queues:
        bot.queues[guild_id].clear()
    if guild_id in bot.loop_states:
        bot.loop_states[guild_id] = False
    if guild_id in bot.now_playing:
        del bot.now_playing[guild_id]
    
    embed = discord.Embed(
        title="⏹️ Stopped",
        description="Music stopped and queue cleared",
        color=0xFFFFFF
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="disconnect", description="Disconnect the bot from voice channel")
async def disconnect_slash(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_connected():
        embed = discord.Embed(
            title="Error",
            description="I'm not connected to a voice channel!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
    
    guild_id = interaction.guild.id
    if guild_id in bot.queues:
        bot.queues[guild_id].clear()
    if guild_id in bot.loop_states:
        bot.loop_states[guild_id] = False
    if guild_id in bot.now_playing:
        del bot.now_playing[guild_id]
    
    await voice_client.disconnect()
    
    embed = discord.Embed(
        title="👋 Disconnected",
        description="Left the voice channel",
        color=0xFFFFFF
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ping", description="Check if bot is responsive")
async def ping_slash(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Bot latency: **{latency}ms**",
        color=0xFFFFFF
    )
    embed.add_field(name="Commands Status", 
                   value="✅ Active" if bot.commands_synced else "⚠️ Syncing...",
                   inline=True)
    embed.add_field(name="Voice Clients", 
                   value=f"{len(bot.voice_clients)} connected",
                   inline=True)
    
    await interaction.response.send_message(embed=embed)

if __name__ == "__main__":
    bot.server_id = 944823319885152296 # your server id
    bot.commands_channel_id =  1449616094707974154 # your channel id here (same goes on top)
    
    NEW_TOKEN = ""  # <-- PUT YOUR NEW TOKEN HERE
    
    try:
        bot.run(NEW_TOKEN, reconnect=True)
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print(f"Bot crashed: {e}")
        print("Restarting in 5 seconds...")
        import time
        time.sleep(5)
        os.execv(sys.executable, ['python'] + sys.argv)
