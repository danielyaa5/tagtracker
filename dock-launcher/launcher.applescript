use AppleScript version "2.4"
use scripting additions

on run
    set trackerUrl to "http://127.0.0.1:8768/"
    
    tell application "System Events"
        set chromeRunning to (exists (processes where name is "Google Chrome"))
    end tell
    
    if chromeRunning then
        try
            tell application "Google Chrome"
                set foundTab to false
                repeat with w in windows
                    set tabIdx to 0
                    repeat with t in tabs of w
                        set tabIdx to tabIdx + 1
                        set u to URL of t
                        if u starts with "http://127.0.0.1:8768" or u starts with "http://localhost:8768" then
                            set active tab index of w to tabIdx
                            set index of w to 1
                            set foundTab to true
                            exit repeat
                        end if
                    end repeat
                    if foundTab then exit repeat
                end repeat
                
                if not foundTab then
                    if (count of windows) is 0 then
                        open location trackerUrl
                    else
                        tell window 1 to make new tab with properties {URL:trackerUrl}
                    end if
                end if
                activate
            end tell
        on error
            do shell script "/usr/bin/open " & quoted form of trackerUrl
        end try
    else
        do shell script "/usr/bin/open " & quoted form of trackerUrl
    end if
    
    tell me to quit
end run
