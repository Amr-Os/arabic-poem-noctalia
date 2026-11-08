-- Desktop widget: the rotating poem image.
-- The image is rendered by renderer/update.py; this entry only displays it.

local dataDir = noctalia.pluginDataDir() or ""
local metaPath = dataDir .. "/render/render.json"
local lastMtime = -1

noctalia.setUpdateInterval(1000)

local function render()
  local raw = noctalia.readFile(metaPath)
  if not raw then
    return
  end
  local meta = noctalia.json.decode(raw)
  if type(meta) ~= "table" then
    return
  end
  local poem = meta.poem
  if type(poem) ~= "table" or type(poem.png) ~= "string" then
    return
  end
  desktopWidget.render(ui.image({
    path = poem.png,
    width = poem.width,
    height = poem.height,
    fit = "contain",
  }))
end

function update()
  local info = noctalia.fileInfo(metaPath)
  if info and info.mtime ~= lastMtime then
    lastMtime = info.mtime
    render()
  end
end

render()
