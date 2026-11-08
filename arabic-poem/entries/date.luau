-- Desktop widget: the Hijri date image.

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
  local date = meta.date
  if type(date) ~= "table" or type(date.png) ~= "string" then
    return
  end
  desktopWidget.render(ui.image({
    path = date.png,
    width = date.width,
    height = date.height,
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
