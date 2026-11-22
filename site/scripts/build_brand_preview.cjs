'use strict';
// Development-only raster export from the reviewed, editable HTML composition.
const {chromium}=require('playwright');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
(async()=>{
 const root=path.resolve(__dirname,'../..');
 const browser=await chromium.launch({headless:true,channel:process.env.DOCFLOW_BROWSER_CHANNEL||'chromium'});
 try{
  const page=await browser.newPage({viewport:{width:1200,height:630},deviceScaleFactor:1});
  await page.goto(pathToFileURL(path.join(root,'docs/brand/SOCIAL_PREVIEW.html')).href);
  await page.evaluate(()=>document.fonts.ready);
  await page.locator('#cover').screenshot({path:path.join(root,'site/dist/assets/social-card.png')});
  await page.setViewportSize({width:32,height:32});
  await page.goto(pathToFileURL(path.join(root,'site/dist/assets/icon.svg')).href);
  await page.evaluate(()=>{document.documentElement.setAttribute('width','32');document.documentElement.setAttribute('height','32');});
  const png=await page.screenshot({omitBackground:true});
  const header=Buffer.alloc(22);header.writeUInt16LE(1,2);header.writeUInt16LE(1,4);header[6]=32;header[7]=32;header.writeUInt16LE(1,10);header.writeUInt16LE(32,12);header.writeUInt32LE(png.length,14);header.writeUInt32LE(22,18);
  await require('node:fs/promises').writeFile(path.join(root,'site/dist/favicon.ico'),Buffer.concat([header,png]));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
