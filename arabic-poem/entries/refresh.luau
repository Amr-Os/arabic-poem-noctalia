-- Optional bar button: rotate the poem immediately.

local pluginDir = noctalia.pluginDir() or ""
local dataDir = noctalia.pluginDataDir() or ""
local python = noctalia.getConfig("python") or "python3"
local script = pluginDir .. "/renderer/update.py"

local function shq(value)
  return "'" .. tostring(value):gsub("'", "'\\''") .. "'"
end

local function run()
  if pluginDir == "" or dataDir == "" then
    noctalia.log("Arabic Poem: pluginDir or pluginDataDir is unavailable")
    return
  end
  local cmd = shq(python)
      .. " " .. shq(script)
      .. " --plugin-dir " .. shq(pluginDir)
      .. " --data-dir " .. shq(dataDir)
      .. " --force"
      .. " --notify"

  local function done(result)
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

  if noctalia.getConfig("notify") == false then
    noctalia.runAsync(cmd)
  else
    noctalia.runAsync(cmd, done)
  end
end

barWidget.setGlyph("refresh")
barWidget.setTooltip("Rotate Arabic poem now")

function onClick()
  run()
end

function onIpc(event, _payload)
  if event == "force" then
    run()
  end
end
