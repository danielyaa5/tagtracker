// Recreate publication media using the real dashboard and fictional demo data.
// Requires Node.js, Playwright, its Chromium browser, Python 3, and ffmpeg.
const {chromium}=require('playwright');
const {spawn,execFileSync}=require('node:child_process');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const ROOT=path.resolve(__dirname,'..'),ASSETS=path.join(ROOT,'site/assets');
(async()=>{
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'tagtracker-media-'));let browser;
 const server=spawn(process.env.PYTHON||'python3',[path.join(__dirname,'demo_server.py'),'--port','0'],{cwd:ROOT});
 server.stderr.on('data',data=>process.stderr.write(data));
 try{
  const url=await new Promise((resolve,reject)=>{server.stdout.once('data',data=>resolve(data.toString().trim()));server.once('exit',code=>reject(Error('Demo server exited: '+code)));});
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}:{})});
  const page=await browser.newPage({viewport:{width:1200,height:1080},deviceScaleFactor:1,timezoneId:'America/Los_Angeles'});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  fs.mkdirSync(ASSETS,{recursive:true});
  async function tiles(){await page.waitForFunction(()=>document.querySelectorAll('img.leaflet-tile').length>0&&[...document.querySelectorAll('img.leaflet-tile')].every(img=>img.complete&&img.naturalWidth>0),{},{timeout:30000});await page.waitForTimeout(300);}
  let frames=[];
  async function frame(seconds=2){const file=path.join(temp,`frame-${frames.length}.png`);await page.screenshot({path:file});frames.push({file,seconds});}
  await page.goto(url);await page.getByRole('link',{name:'Demo backpack',exact:true}).waitFor();
  await page.screenshot({path:path.join(ASSETS,'overview.png'),fullPage:true});
  await page.getByRole('link',{name:'Demo backpack',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#map-status').textContent.startsWith('4 observations'));await tiles();await frame(2.2);
  await page.selectOption('#range','7d');await page.waitForFunction(()=>document.querySelector('#map-status').textContent.startsWith('8 observations'));await tiles();await frame(2.2);
  await page.selectOption('#range','all');await page.waitForFunction(()=>document.querySelector('#map-status').textContent.startsWith('10 observations'));await tiles();
  await page.screenshot({path:path.join(ASSETS,'history.png'),fullPage:true});await frame(2.2);
  await page.locator('.leaflet-interactive').first().click();await page.locator('.leaflet-popup').waitFor();await frame(2.2);
  await page.locator('.leaflet-popup-close-button').click();await page.getByRole('button',{name:'Fit all points'}).click();await tiles();await frame(1.8);
  await page.getByRole('link',{name:'← Back to all items'}).click();await page.getByRole('link',{name:'Demo backpack',exact:true}).waitFor();await frame(1.4);
  if(errors.length)throw Error(errors.join('\n'));
  const list=path.join(temp,'frames.txt');fs.writeFileSync(list,frames.map(f=>`file '${f.file}'\nduration ${f.seconds}\n`).join('')+`file '${frames.at(-1).file}'\n`);
  execFileSync(process.env.FFMPEG||'ffmpeg',['-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',list,'-filter_complex','fps=5,scale=1000:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4','-loop','0',path.join(ASSETS,'demo.gif')]);
  console.log('Created overview.png, history.png and demo.gif from actual dashboard interactions. No JavaScript errors.');
 }finally{
  if(browser)await browser.close();
  if(server.exitCode===null){const stopped=new Promise(resolve=>server.once('exit',resolve));server.kill('SIGINT');await stopped;}
  fs.rmSync(temp,{recursive:true,force:true});
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
