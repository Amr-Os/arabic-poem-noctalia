-- Desktop widget: the Arabic weekday image.

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
  local weekday = meta.weekday
  if type(weekday) ~= "table" or type(weekday.png) ~= "string" then
    return
  end
  desktopWidget.render(ui.image({
    path = weekday.png,
    width = weekday.width,
    height = weekday.height,
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
