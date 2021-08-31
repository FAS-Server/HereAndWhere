import re
from typing import Optional, Tuple

from mcdreforged.api.utils import Serializable
from mcdreforged.api.types import PluginServerInterface, ServerInterface, PlayerCommandSource
from mcdreforged.api.rtext import RText, RAction, RTextList, RColor
from mcdreforged.api.command import Literal, Text
from mcdreforged.api.decorator import new_thread

from here_and_where.dimension import get_dimension, Dimension, LegacyDimension
import minecraft_data_api as api


class Config(Serializable):
    highlight_time: int = 15
    display_voxel_waypoint: bool = True
    display_xaero_waypoint: bool = True
    click_to_teleport: bool = False


config: Config
CONFIG_FILE = 'config/here_and_where.json'
here_user = 0


def process_coordinate(text: str) -> tuple:
    data = text[1:-1].replace('d', '').split(', ')
    data = [(x + 'E0').split('E') for x in data]
    return tuple([float(e[0]) * 10 ** int(e[1]) for e in data])


def process_dimension(text: str) -> str:
    return text.replace(re.match(r'[\w ]+: ', text).group(), '', 1)


def coordinate_text(x: float, y: float, z: float, dimension: Dimension):
    coord = RText('[{}, {}, {}]'.format(int(x), int(y), int(z)), dimension.get_coordinate_color())
    if config.click_to_teleport:
        return (
            coord.h(dimension.get_rtext() + ': 点击以传送到' + coord.copy()).
            c(RAction.suggest_command,
              '/execute in {} run tp {} {} {}'.format(dimension.get_reg_key(), int(x), int(y), int(z)))
        )
    else:
        return coord.h(dimension.get_rtext())


def __display(server: ServerInterface, name: str, position: Tuple[float, float, float], dimension_str: str,
              display_to: Optional[PlayerCommandSource] = None, highlight: Optional[bool] = None):
    x, y, z = position
    dimension = get_dimension(dimension_str)

    # basic text: someone @ dimension [x, y, z]
    texts = RTextList(RText(name, RColor.yellow), ' @ ', dimension.get_rtext(), ' ',
                      coordinate_text(x, y, z, dimension))

    # click event to add waypoint
    if config.display_voxel_waypoint:
        texts.append(' ', RText('[+V]', RColor.aqua).h('§bVoxelmap§r: 点此以高亮坐标点, 或者Ctrl点击添加路径点').c(
            RAction.run_command, '/newWaypoint x:{}, y:{}, z:{}, dim:{}'.format(
                int(x), int(y), int(z), dimension.get_reg_key()
            )
        ))
    if config.display_xaero_waypoint:
        command = "xaero_waypoint_add:{}'s Location:{}:{}:{}:{}:6:false:0".format(name, name[0], int(x), int(y), int(z))
        if isinstance(dimension, LegacyDimension):
            command += ':Internal_{}_waypoints'.format(dimension.get_reg_key().replace('minecraft:', '').strip())
        texts.append(' ', RText('[+X]', RColor.gold).h('§6Xaeros Minimap§r: 点击添加路径点').c(RAction.run_command, command))

    # coordinate conversion between overworld and nether
    if dimension.has_opposite():
        oppo_dim = dimension.get_opposite()
        if oppo_dim.get_id() == -1:
            coord_text = coordinate_text(x/8, y/8, z/8, oppo_dim)
        else:
            coord_text = coordinate_text(x*8, y*8, z*8, oppo_dim)
        arrow = RText('->', RColor.gray)
        texts.append(RText.format(
            ' {} {}',
            arrow.copy().h(RText.format('{} {} {}', dimension.get_rtext(), arrow, oppo_dim.get_rtext())),
            coord_text
        ))

    if display_to:
        display_to.reply(texts)
    else:
        server.say(texts)
    # highlight
    if highlight and config.highlight_time > 0:
        server.execute('effect give {} minecraft:glowing {} 0 true'.format(name, config.highlight_time))


@new_thread('where_and_here#display')
def display(server: PluginServerInterface, name: str, display_to: Optional[PlayerCommandSource] = None,
            highlight: Optional[bool] = None):
    if check_player(name):
        coords = api.get_player_coordinate(name)
        dimension = api.get_player_dimension(name)
        __display(server, name, coords, dimension, display_to, highlight)
    else:
        server.logger.info('no such player')


def check_player(player: str) -> bool:
    ServerInterface.get_instance().logger.info(f'check_player {player}')
    # try:
    total, limit, player_list = api.get_server_player_list()
    ServerInterface.get_instance().logger.info(f"players: {','.join(player_list)}")
    return player in player_list
    # except:
    #     return False


def register_command(server: PluginServerInterface):
    where_node = Literal("!!where").runs(lambda src: src.reply('需要指定要查找的玩家名!')).then(
        Text('player').runs(
            lambda src, ctx: display(server, ctx['player'], src, False)
        ).then(
            Literal('-s').runs(lambda src, ctx: display(server, ctx['player'], src, False))
        ).then(
            Literal('-a').runs(lambda src, ctx: display(server, ctx['player'], highlight=False))
        ))

    here_node = Literal("!!here").requires(lambda src: src.is_player, lambda: '只能由玩家执行此命令!').runs(
        lambda src: display(server, src.player, highlight=True)
    )

    server.register_command(where_node)
    server.register_command(here_node)
    server.register_help_message('!!here', '广播自身坐标并高亮')
    server.register_help_message('!!where', '查询玩家坐标')


def on_load(server: PluginServerInterface, old):
    global config
    register_command(server)
    config = server.load_config_simple(CONFIG_FILE, target_class=Config, in_data_folder=False)
