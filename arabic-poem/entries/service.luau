-- Arabic Poem service: checks rotation/date on a timer and handles IPC.
-- All Arabic shaping happens in Python/Pango; this entry only launches it.

local pluginDir = noctalia.pluginDir() or ""
local dataDir = noctalia.pluginDataDir() or ""
local python = noctalia.getConfig("python") or "python3"
local interval = tonumber(noctalia.getConfig("interval_minutes")) or 5
interval = math.max(1, math.min(60, interval))

local script = pluginDir .. "/renderer/update.py"
local metaPath = dataDir .. "/render/render.json"

local function shq(value)
  return "'" .. tostring(value):gsub("'", "'\\''") .. "'"
end

local function run(flag, cb)
  if pluginDir == "" or dataDir == "" then
    noctalia.log("Arabic Poem: pluginDir or pluginDataDir is unavailable")
    return false
  end
  local cmd = shq(python)
      .. " " .. shq(script)
      .. " --plugin-dir " .. shq(pluginDir)
      .. " --data-dir " .. shq(dataDir)
      .. " " .. flag
      .. " --notify"
  if cb then
    return noctalia.runAsync(cmd, cb)
  end
  return noctalia.runAsync(cmd)
end

local function status()
  local raw = noctalia.readFile(metaPath)
  if not raw then
    noctalia.notify("Arabic Poem", "No render yet.\nData: " .. dataDir)
    return
  end
  local meta, err = noctalia.json.decode(raw)
  if type(meta) ~= "table" then
    noctalia.notify(
      "Arabic Poem",
      "Could not read render metadata: " .. tostring(err or "invalid JSON")
    )
    return
  end
  local poem = type(meta.poem) == "table" and meta.poem or {}
  local date = type(meta.date) == "table" and meta.date or {}
  local weekday = type(meta.weekday) == "table" and meta.weekday or {}
  local lines = {
    "Data: " .. dataDir,
    "Poem: " .. tostring(poem.id or "?"),
    "Font: " .. tostring(poem.font or "?"),
    "Date: " .. tostring(date.date_iso or "?"),
    "Weekday index: " .. tostring(weekday.weekday_index or "?"),
  }
  noctalia.notify("Arabic Poem", table.concat(lines, "\n"))
end

local function notify_result(result)
  if type(result) ~= "table" then
    return
  end
  if result.timedOut then
    noctalia.notify("Arabic Poem", "Render started; check the desktop widget.")
  elseif result.exitCode == 0 then
    local out = (result.stdout or ""):gsub("%s+$", "")
    if out == "" then
      out = "Poem refreshed."
    end
    noctalia.notify("Arabic Poem", out)
  else
    local err = (result.stderr or ""):gsub("%s+$", "")
    if err == "" then
      err = "Renderer failed with exit code " .. tostring(result.exitCode)
    end
    noctalia.notifyError("Arabic Poem", err)
  end
end

local function manual(flag)
  if noctalia.getConfig("notify") == false then
    run(flag)
  else
    run(flag, notify_result)
  end
end

noctalia.setUpdateInterval(interval * 60 * 1000)

function update()
  run("--if-due")
end

function onIpc(event, _payload)
  if event == "force" then
    manual("--force")
  elseif event == "refresh" then
    manual("--refresh")
  elseif event == "status" then
    status()
  else
    noctalia.log("Arabic Poem: unknown IPC event " .. tostring(event))
  end
end

-- Render immediately on load so the desktop widgets do not wait for a tick.
run("--if-due")
