"""
城鎮建築、共用小件、室內家具的概念圖：白底單棟、斜上方四分之三視角，拿 Provencal 參考圖當畫風。
使用者看過點頭的才送 art_pipeline/meshy/generate.py。輸出到 art_source/concepts/towns/<城鎮>_<名字>_<種子>.png，
另外拼一張 <城鎮>_sheet_<種子>.png 給人看，總覽圖不進版本庫。

用法：python art_pipeline/meshy/concepts.py <城鎮> [種子]
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from comfy import flux  # noqa: E402

OUT = os.path.join(flux.PROJECT_ROOT, "art_source", "concepts", "towns")

FRAME = ("A single stylized fantasy {what} as a game asset, isolated on a plain white background, three-quarter view "
         "from slightly above, the whole building visible, no ground scenery, no people. {design} "
         "Soft hand-painted stylized look with clean chunky shapes and gentle bevels, in the painterly style of the "
         "reference image, no text.")

TOWNS = {
    "dawn": {
        "inn": ("village inn", "Two and a half storeys, whitewashed lime plaster ground floor with pale grey stone corner blocks, dark timber upper floors with small balconies, terracotta barrel tile roof with blue painted eave edges, a hanging wooden sign with a mug, blue shutters, flower boxes, ivy."),
        "smithy": ("village blacksmith", "Low stone and plaster workshop with a big open front under a wide terracotta tile awning on dark wooden posts, a stone chimney with smoke, an anvil and barrels by the entrance, blue painted door, terracotta roof with blue eave edges."),
        "storage": ("village warehouse", "Tall stone and plaster storehouse with a wooden hoist beam and rope at the top, big double blue wooden doors, crates stacked beside, terracotta tile roof with blue eave edge, small windows."),
        "town_hall": ("village town hall", "Grand but cosy whitewashed hall with a round stone clock tower on one side topped by a wide conical terracotta roof on wooden corbels, arched windows with blue shutters, stone steps, banners, ivy."),
        "item_shop": ("village general store", "Small whitewashed shop with a striped cream and blue cloth awning over the front counter, shelves of potions and jars in the window, terracotta tile roof with blue eave edges, a hanging sign with a potion bottle."),
        "house_2": ("village cottage", "One storey whitewashed cottage on a stone base, arched blue door, round window, terracotta tile roof with blue eave edges, a small lean-to wood shed on the side, ivy and flowers."),
        "house_3": ("round tower house", "A round whitewashed stone tower house, three storeys, with a wooden balcony and outriggers near the top, conical terracotta tile roof with a blue edge, arched blue door, small arched windows, ivy climbing."),
        "windmill": ("village windmill", "Round whitewashed stone windmill with four white cloth sails on a wooden frame, conical terracotta cap roof, blue door, small windows."),
    },
    "magic": {
        "academy_tower": ("tall magic academy tower", "Slender whitewashed tower with dark timber bands, many arched windows glowing softly, a pointed slate-blue conical roof, an open observatory platform near the top with a brass telescope, floating small crystals around the tip."),
        "observatory": ("wizard observatory", "Round stone and plaster building with a big domed slate-blue roof that has an open slit and a large brass telescope, star patterns painted in gold on the dome, arched door."),
        "academy_hall": ("magic academy great hall", "Long whitewashed hall with dark timber framing and tall arched windows with purple-blue stained glass, slate-blue roof with small spires, a big arched entrance with a glowing rune above it."),
        "canal_house": ("canal-side town house", "Narrow three storey whitewashed house with dark timber framing standing on a stone quay, many small windows, a slate-blue roof, a little wooden dock with a rowing boat, lanterns."),
        "bookshop": ("magic bookshop", "Crooked cosy shop with books stacked in the bay window, a hanging sign shaped like an open book, dark timber and whitewash, slate-blue roof, glowing lantern, a few floating pages."),
        "bridge": ("stone arch canal bridge", "Humpbacked stone arch bridge over a short canal segment, lanterns on posts at both ends, low parapet walls, moss on the stones."),
        "crystal_well": ("magic crystal fountain", "Round stone fountain with a large softly glowing blue crystal in the middle, runes carved on the rim, water pouring."),
    },
    "parts": {
        "market_stall": ("village market stall", "Small wooden market stall with a slanted terracotta tile roof with blue eave edge on four dark wooden posts, a counter with baskets of fruit and bread, crates underneath."),
        "awning": ("striped cloth shop awning", "A standalone slanted cloth awning with cream and faded blue stripes on a thin dark wooden frame with two front posts, scalloped front edge, meant to attach to a wall."),
        "balcony": ("wooden house balcony", "A standalone small wooden balcony with dark weathered planks, a simple railing, two diagonal support brackets underneath, a flower box with red flowers on the railing, meant to attach to a wall."),
        "stairs": ("stone outdoor stairs", "A short flight of pale grey rounded stone steps with low side walls, a bit of moss and grass between the stones."),
        "well": ("village water well", "Round pale grey stone well with a small terracotta tile roof on two dark wooden posts, a wooden bucket on a rope and a crank."),
        "torii": ("red Japanese torii gate", "A vermilion red torii gate with a black top beam, standing on two small stone bases, a straw rope with white paper streamers."),
        "stone_lantern": ("Japanese stone lantern", "A grey stone toro lantern with a wide roof cap and a small window, a little moss on the top."),
    },
    "keep": {
        "gatehouse": ("fortress gatehouse of a knights order", "Massive grey limestone gatehouse with a heavy wooden gate and iron studs, two squat round towers with crenellations, no plaster, red and gold cloth banners hanging, a wooden portcullis."),
        "barracks": ("knights barracks", "Long low grey stone barracks with a dark slate roof, small deep windows, a wooden weapon rack with spears and shields leaning outside, a banner by the door."),
        "great_hall": ("knights commander hall", "Tall grey stone hall with a steep dark slate roof, a big round rose window, heavy buttresses, stone steps up to double wooden doors, long red banners with a sword emblem."),
        "watchtower": ("square stone watchtower", "Tall square grey limestone tower with crenellations at the top, arrow slit windows, a wooden lookout roof on top, a banner pole."),
        "forge": ("fortress armory forge", "Open-fronted grey stone forge with a big chimney and glowing furnace, anvils, racks of swords and shields, a dark slate roof on thick timber posts."),
        "oath_stone": ("ancient oath stone platform", "A circular stone platform with a tall carved standing stone in the middle, a sword planted in front of it, small stone steps, banners on poles around it."),
    },
    "highbough": {
        "tree_platform": ("treetop wooden platform house", "A small wooden hut with a mossy shingle roof built on a round wooden platform wrapped around a huge tree trunk, rope railings, a rope ladder hanging down, lanterns."),
        "rope_bridge": ("wooden rope bridge segment", "A short sagging rope bridge with wooden plank walkway and rope railings between two wooden posts, some moss on the planks."),
        "lookout": ("treetop lookout tower", "A tall wooden lookout nest on stilts made of rough logs, a small shingle roof, a rope ladder, a hanging horn and a small flag."),
        "stilt_hut": ("hunter hut on stilts", "Wooden hunter hut on four tall log stilts with a steep mossy shingle roof, a ladder, hanging drying furs and a bow rack, a small porch."),
        "ladder_post": ("wooden ladder tower", "A tall wooden ladder scaffold with two landings wrapped in rope, lanterns hanging, for climbing between tree levels."),
    },
    "lanternford": {
        "chapel": ("riverside chapel", "Low whitewashed chapel with wooden posts and a very long overhanging grey-green shingle roof sheltering a covered walkway, a small wooden bell tower, warm lanterns hanging along the eaves."),
        "almshouse": ("long whitewashed almshouse", "Long one storey whitewashed house with dark wooden posts, a long overhanging roof covering a porch walkway, many small windows, benches and potted herbs on the porch, lanterns."),
        "covered_bridge": ("covered wooden bridge", "A long wooden bridge with a pitched grey-green shingle roof on posts over it, two rows of hanging paper lanterns inside, stone piers underneath."),
        "bell_tower": ("tall wooden bell tower", "Tall slender whitewashed bell tower with a wooden upper frame holding a bronze bell, a pointed grey-green shingle roof, a lantern at the top."),
        "boathouse": ("river boathouse and ferry dock", "Small wooden boathouse on stilts over water with a long roof, a wooden dock with a flat ferry boat moored, lanterns on poles, rope coils."),
        "herb_shop": ("herbalist apothecary", "Small whitewashed shop with a long roof over the front, bundles of drying herbs hanging under the eaves, jars on shelves, a mortar sign, lanterns."),
    },
    "street": {
        "bench": ("wooden park bench", "A simple sturdy wooden bench with thick dark weathered planks and stone legs, a little moss."),
        "barrel": ("wooden barrel", "A single wooden barrel with dark iron hoops, weathered warm brown staves, lid on top."),
        "barrels": ("pair of barrels", "Two wooden barrels side by side with dark iron hoops, one with a lid and one open with apples inside."),
        "cart": ("wooden hand cart", "A wooden two-wheeled hand cart loaded with a few sacks and a crate, dark weathered wood, spoked wheels."),
        "wall": ("town wall segment", "A straight segment of a town wall, pale grey rough stone blocks with a whitewashed upper part and a row of terracotta tiles on top, a little ivy, about four times wider than tall."),
        "wall_tower": ("round town wall tower", "A short round pale grey stone wall tower with a conical terracotta tile roof with blue eave edge, small arrow slit windows, ivy."),
        "lamp_post": ("street lamp post", "A dark iron street lamp post on a stone base with a warm glowing glass lantern on top."),
        "flower_pots": ("group of three flower pots", "Only three terracotta flower pots standing together on the ground with red geraniums, lavender and green herbs, nothing else, no building, no wall."),
    },
    "furniture": {
        "counter": ("shop counter", "A sturdy wooden shop counter with a worn top, a small brass bell, a ledger book and a few potion bottles on it, drawers in front."),
        "shelf": ("tall shop shelf", "A tall dark wooden shelf full of colourful potion bottles, jars, boxes and scrolls."),
        "bookshelf": ("tall bookshelf", "A tall wooden bookshelf packed with old books of many colours, a few scrolls and a candle."),
        "table_set": ("tavern table with chairs", "A round wooden tavern table with two wooden stools, mugs and a plate of bread on it."),
        "bed": ("simple wooden bed", "A simple wooden bed with a thick cream quilt and a blue blanket folded at the end, a pillow."),
        "fireplace": ("stone fireplace", "A cosy stone fireplace with a wooden mantel, a glowing fire and a hanging pot, a few logs beside it."),
        "anvil_set": ("blacksmith anvil and tools", "An iron anvil on a tree stump with a hammer and tongs, a small water barrel and a sword rack beside it."),
        "crates": ("storage crates and sacks", "A pile of wooden crates, grain sacks and a barrel stacked together."),
        "altar": ("small church altar", "A stone altar with a white cloth, two candles, a small sprout emblem carved on the front and a bowl of water."),
        "desk": ("scholar desk", "A wooden writing desk covered with open books, a quill and ink, a brass globe and a candle, with a chair."),
        "weapon_rack": ("weapon rack", "A wooden weapon rack holding swords, spears and a round shield."),
        "low_table": ("Japanese low table", "A low Japanese wooden table on a tatami mat with two flat floor cushions and a tea set."),
        "kakejiku": ("Japanese alcove with scroll", "A Japanese tokonoma alcove with a hanging calligraphy scroll, a small ikebana vase and a wooden step."),
        "sword_stand": ("Japanese katana stand", "A lacquered black wooden katana stand holding two katanas, on a small low platform."),
    },
    "japan": {
        "dojo": ("Japanese sword dojo", "Wooden dojo hall with a large grey-blue kawara tile roof with upturned ends, raised wooden floor and verandah, sliding doors open, a wooden signboard above the entrance, sword rack visible."),
        "onmyo_office": ("onmyoji bureau office", "Stately Heian style wooden building with vermilion pillars and white walls, cypress bark roof, hanging paper talismans, a raised floor with stairs, a small stone lantern."),
        "ninja_house": ("hidden ninja house", "Modest dark wooden farmhouse with a thick thatched roof, bamboo fence, hidden wooden trapdoor and a rope on the side, a straw hat hanging, subtle and quiet."),
        "ascetic_hall": ("mountain ascetic hall", "Small wooden mountain temple hall on a stone base with a steep thatched roof, a large conch shell and wooden staff by the door, white paper streamers, stone steps and moss."),
        "inn_b": ("Japanese ryokan inn", "Two storey wooden inn with clean simple grey-blue kawara tile roofs with neat straight tile rows, sliding paper doors, wooden verandah, red paper lanterns, a small pine tree."),
        "machiya": ("traditional Japanese town house", "Two storey wooden machiya with dark brown lattice front, white plaster upper wall, grey-blue kawara tile roof with curved ends, noren curtain at the entrance, paper lantern."),
        "inn": ("Japanese ryokan inn", "Two storey wooden inn with a wide grey-blue kawara tile roof and a smaller roof over the entrance, sliding paper doors, wooden verandah, red paper lanterns, a small pine tree."),
        "pagoda": ("Japanese five storey pagoda", "Tall slender wooden pagoda with five stacked grey-blue tile roofs with upturned corners, vermilion red posts and beams, a bronze spire on top."),
        "shrine": ("Japanese shinto shrine", "Small shrine hall with a sweeping copper-green roof, vermilion red pillars, a rope with white paper streamers, stone lanterns, with a red torii gate in front."),
        "forge": ("Japanese sword smith forge", "Wooden workshop with an open front, a clay furnace with a chimney, grey tile roof, bamboo fence, hanging straw rope, charcoal sacks."),
        "gate": ("Japanese town gate", "Large wooden gate with a heavy grey-blue tile roof, thick dark wooden pillars, white plaster side walls on a stone base, hanging lanterns."),
        "tea_house": ("Japanese tea house", "Small wooden tea house with a thatched roof, round window, bamboo fence, red parasol and bench outside, stepping stones."),
    },
}


def label_sheet(town, names, seed):
    size = 384
    sheet = Image.new("RGB", (size * 4, (size + 36) * ((len(names) + 3) // 4)), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except OSError:
        font = None
    for i, name in enumerate(names):
        img = Image.open(os.path.join(OUT, "%s_%s_%d.png" % (town, name, seed))).resize((size, size))
        x, y = (i % 4) * size, (i // 4) * (size + 36)
        sheet.paste(img, (x, y))
        draw.text((x + 10, y + size + 4), name, fill=(40, 40, 40), font=font)
    sheet.save(os.path.join(OUT, "_sheet_%s_%d.png" % (town, seed)))


if __name__ == "__main__":
    town = sys.argv[1]
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    ref = flux.upload(flux.STYLE_REF)
    names = list(TOWNS[town])
    for name in names:
        what, design = TOWNS[town][name]
        path = os.path.join(OUT, "%s_%s_%d.png" % (town, name, seed))
        if not os.path.exists(path):
            flux.run(flux.graph(FRAME.format(what=what, design=design), ref, seed, size=1024)).save(path)
        print(town, name, "ok", flush=True)
    label_sheet(town, names, seed)
