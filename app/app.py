import discord
import random
from discord.ext import commands
from discord.ui import View, Button
import os
from dotenv import load_dotenv
from keep_alive import keep_alive
load_dotenv()
# ボットの設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ゲーム用のクラス
class Player:
    def __init__(self, name, user_id, user):
        self.name = name
        self.hp = 100
        self.attack_power = 30
        self.alive = True
        self.user_id = user_id
        self.user = user
        self.selected_number = None

    def take_damage(self, damage):
        self.hp -= damage
        if self.hp <= 0:
            self.alive = False
            return f"{self.name} は死亡しました！"
        return f"{self.name} は{damage}のダメージを受け、現在HPは{self.hp}です。"

    def is_alive(self):
        return self.alive

class Game:
    def __init__(self):
        self.players = []
        self.round = 1
        self.skip_rounds = 0

    def add_player(self, player):
        self.players.append(player)

    def reset_game(self):
        self.players = []
        self.round = 1
        self.skip_rounds = 0

    def start_round(self):
        target_number = random.randint(1, 10)  # ランダムな目標値を生成

        result = f"--- ラウンド {self.round} ---\n目標値: {target_number}\n"

        # プレイヤーが選んだ数字を表示
        result += "\n".join([f"{player.name} は {player.selected_number} を選びました。" for player in self.players if player.is_alive()])

        # 目標値に最も近い数字を選んだプレイヤーを決定
        closest_players = [
            p for p in self.players if p.is_alive() and abs(p.selected_number - target_number) == min(
                abs(p.selected_number - target_number) for p in self.players if p.is_alive()
            )
        ]

        if len(closest_players) > 1:  # 同じ距離のプレイヤーが複数いる場合
            self.skip_rounds += 1
            result += "\n複数のプレイヤーが目標値に最も近いため、このラウンドはスキップされます！"
            return result, None

        closest_player = closest_players[0]
        result += f"\n最も目標値に近いのは {closest_player.name} です！強撃権を持ちます。"
        self.skip_rounds = 0  # スキップカウントをリセット
        return result, closest_player

    def check_end_game(self):
        alive_players = [p for p in self.players if p.is_alive()]
        if len(alive_players) == 1:
            return True, alive_players[0]
        return False, None

# 攻撃対象選択用のView
class TargetSelectView(View):
    def __init__(self, attacker, targets):
        super().__init__(timeout=60)
        self.attacker = attacker
        self.targets = targets

        for target in targets:
            button = Button(label=target.name, style=discord.ButtonStyle.primary)

            async def button_callback(interaction: discord.Interaction, target=target):
                if interaction.user.id != self.attacker.user_id:
                    await interaction.response.send_message("これはあなたのターンではありません。", ephemeral=True)
                    return

                damage = self.attacker.attack_power
                result = target.take_damage(damage)
                await interaction.response.send_message(f"{self.attacker.name} が {target.name} を攻撃しました！\n{result}")

                if not target.is_alive():
                    await interaction.channel.send(f"{target.name} は死亡しました！")
                self.stop()

                # ゲームの終了確認
                is_game_over, winner = game.check_end_game()
                if is_game_over:
                    await interaction.channel.send(f"ゲームが終了しました！勝者: {winner.name}")
                    game.reset_game()
                else:
                    await start_round(interaction)

            button.callback = button_callback
            self.add_item(button)

# ゲームオブジェクトを作成
game = Game()

async def collect_numbers(interaction):
    """プレイヤー全員から数字を収集する
    """
    for player in game.players:
        if player.is_alive():
            await player.user.send("1から10の数字を入力してください。")
            try:
                response = await bot.wait_for(
                    "message",
                    check=lambda m: m.author.id == player.user_id and m.channel.type == discord.ChannelType.private
                )
                selected_number = int(response.content)
                if 1 <= selected_number <= 10:
                    player.selected_number = selected_number
                    await player.user.send(f"あなたは {selected_number} を選びました！")
                else:
                    await player.user.send("無効な数字です。1から10の数字を入力してください。")
                    return await collect_numbers(interaction)
            except (ValueError, TimeoutError):
                await player.user.send("無効な入力または時間切れです。1から10の数字を再入力してください。")
                return await collect_numbers(interaction)

async def start_round(interaction):
    """ゲームラウンドの進行
    """
    await collect_numbers(interaction)
    result, closest_player = game.start_round()

    # 各プレイヤーにラウンドの結果を通知
    for player in game.players:
        await player.user.send(result)

    if closest_player:
        await process_attack(interaction, closest_player)
    else:
        if game.skip_rounds == 2:
            await handle_skipped_rounds(interaction)
            await interaction.channel.send("全員に30ダメージが与えられました！")


        is_game_over, winner = game.check_end_game()
        if is_game_over:
            game.reset_game()
        else:
            # 次のラウンドを開始
            await interaction.channel.send("次のラウンドを開始します。")
            await start_round(interaction)

async def process_attack(interaction, closest_player):
    """攻撃処理
    """
    targets = [p for p in game.players if p.is_alive() and p != closest_player]
    if targets:
        view = TargetSelectView(attacker=closest_player, targets=targets)
        await closest_player.user.send("攻撃対象を選択してください。", view=view)
    else:
        await closest_player.user.send("攻撃対象がいません。次のラウンドに進みます。")

async def handle_skipped_rounds(interaction):
    """連続スキップ時の処理
    """
    for player in game.players:
        if player.is_alive():
            result = player.take_damage(30)
            await player.user.send("ラウンドが2回連続でスキップされたため、全員に30ダメージが与えられました！")
            await player.user.send(result)

    is_game_over, winner = game.check_end_game()
    if is_game_over:
        await interaction.channel.send(f"ゲームが終了しました！勝者: {winner.name}")
        game.reset_game()

@bot.tree.command(name="join")
async def join_game(interaction: discord.Interaction):
    player_name = interaction.user.name
    if player_name not in [p.name for p in game.players]:
        game.add_player(Player(player_name, interaction.user.id, interaction.user))
        await interaction.response.send_message(f"{player_name} がゲームに参加しました！", ephemeral=True)
    else:
        await interaction.response.send_message(f"{player_name} は既にゲームに参加しています。", ephemeral=True)

@bot.tree.command(name="start")
async def start_game(interaction: discord.Interaction):
    if len(game.players) < 2:
        await interaction.response.send_message("参加者が2人以上必要です。", ephemeral=True)
        return

    for player in game.players:
        await player.user.send("ゲームを開始します！")
    await start_round(interaction)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'ログインしました: {bot.user}')

keep_alive()
bot.run(os.getenv("TOKEN"))
