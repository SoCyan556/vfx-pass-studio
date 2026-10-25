// UI flow tests use real pass images with an isolated desktop transport.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
(async()=>{
 const root=__dirname,fixture=JSON.parse(fs.readFileSync(path.join(root,'test-artifacts/ui-fixture.json'),'utf8'));
 const browser=await chromium.launch({headless:true,channel:'msedge',args:['--disable-gpu']});
 const page=await browser.newPage({viewport:{width:1460,height:960},deviceScaleFactor:1});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(data=>{
  window._test={events:[],saved:[],busy:false,actions:[],cancelExport:true};
  window.pywebview={api:{bootstrap:async()=>data.bootstrap,frame:async(n,i)=>data.frames[n][i]||null,
   poll:async()=>({events:window._test.events.splice(0),busy:window._test.busy}),
   save_settings:async s=>{window._test.saved.push(s);return {ok:true}},
   browse_video:async()=>({video:{name:'Your footage.mov',path:'C:/clips/Your footage.mov',width:1920,height:1080,fps:'24000/1001',duration:4.2,has_alpha:false},alpha:'Anime subject'}),
   choose_folder:async k=>k==='export'?{package:data.bootstrap.package}:{path:'C:/exports'},
   choose_matte:async()=>({path:'C:/clips/matte.mov'}),
   start:async(s,p)=>{window._test.busy=true;window._test.actions.push({start:s,preview:p});return {ok:true}},
   stop:async()=>{window._test.busy=false;window._test.events.push({type:'cancelled'});return {ok:true}},
   export_passes:async()=>{window._test.actions.push('export_dialog');if(window._test.cancelExport){window._test.cancelExport=false;return {cancelled:true}}setTimeout(()=>window._test.events.push({type:'export_progress',progress:.5}),100);setTimeout(()=>window._test.events.push({type:'export_complete',path:'C:/exports/shot.zip'}),700);return {ok:true}},
   open_output:async()=>window._test.actions.push('open_output'),window_action:async a=>window._test.actions.push(a)
  }};
 },fixture);
 await page.goto(pathToFileURL(path.join(root,'ui/index.html')).href);await page.waitForFunction(()=>studio.ready);
 await page.waitForTimeout(750);
 assert.equal(await page.evaluate(()=>studio.getState().screen),'setup');
 assert.equal(await page.locator('.eyebrow,.field-note,.drop-hint,.progress-footnote,.brand p,.workspace-footer').count(),0);
 assert.ok(await page.locator('.setup-screen').isVisible());assert.equal(await page.locator('.preview-screen').isVisible(),false);
 assert.ok(await page.locator('.drop-emblem .fang-logo image').evaluate(el=>el.href.baseVal.endsWith('fangs-transparent.png')));
 assert.equal(await page.locator('body').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(5, 5, 5)');
 await page.screenshot({path:path.join(root,'test-artifacts/red-setup.png')});
 await page.locator('#generate').click();assert.equal(await page.locator('#generation-overlay').isVisible(),false);
 await page.locator('#browse').click();assert.equal(await page.locator('#file-name').textContent(),'Your footage.mov');
 await page.locator('#settings-heading').click();await page.waitForTimeout(600);
 const drawer=page.locator('#settings-drawer');await drawer.locator('[data-select=materials]').click();await page.locator('#popover [data-value="AI estimates"]').click();
 assert.equal(await page.evaluate(()=>studio.getState().settings.materials),'AI estimates');
 await drawer.locator('[data-select=materials]').click();await page.locator('#popover [data-value="SuperMat estimates"]').click();
 await page.locator('#steps').fill('8');await page.locator('#steps').dispatchEvent('input');
 await page.locator('#save-settings').click();await page.waitForTimeout(400);assert.equal(await page.evaluate(()=>_test.saved.at(-1).steps),8);
 await page.locator('#generate').click();await page.waitForFunction(()=>studio.getState().busy);
 assert.ok(await page.locator('#generation-overlay').isVisible());assert.ok(await page.locator('#workspace').evaluate(el=>el.inert));
 await page.evaluate(()=>_test.events.push({phase:'Normals',message:'Normals · frame 2 / 3',current:1,total:3,progress:.4}));
 await page.waitForFunction(()=>document.getElementById('progress-track').getAttribute('aria-valuenow')==='40');
 await page.waitForTimeout(1000);assert.equal(await page.locator('#phase-percent').textContent(),'40%','No fake progress while waiting');
 await page.evaluate(()=>_test.events.push({phase:'Normals',message:'Model loading',current:0,total:0,progress:.3,indeterminate:true}));
 await page.waitForTimeout(400);assert.equal(await page.locator('#phase-percent').textContent(),'40%','Progress never moves backwards');
 await page.screenshot({path:path.join(root,'test-artifacts/red-progress.png')});
 await page.locator('#cancel').click();await page.waitForFunction(()=>!studio.getState().busy);assert.equal(await page.locator('#generation-overlay').isVisible(),false);
 await page.locator('#generate').click();await page.evaluate(p=>{_test.busy=false;_test.events.push({type:'complete',package:p});},fixture.bootstrap.package);
 await page.waitForFunction(()=>studio.getState().screen==='preview'&&!studio.getState().busy);
 assert.equal(await page.locator('.setup-screen').isVisible(),false);assert.ok(await page.locator('#export-passes').isVisible());
 assert.equal(await page.locator('.pass-card img:not([hidden])').count(),8);
 await page.locator('[data-pass=metallic]').click();await page.waitForTimeout(500);assert.equal(await page.evaluate(()=>studio.getState().currentPass),'metallic');
 await page.locator('[data-pass=basecolor]').hover();await page.waitForTimeout(400);assert.notEqual(await page.locator('[data-pass=basecolor]').evaluate(el=>getComputedStyle(el).transform),'none');
 await page.locator('#scrubber').fill('2');await page.locator('#scrubber').dispatchEvent('input');assert.equal(await page.evaluate(()=>studio.getState().frame),2);
 await page.locator('#export-passes').click();await page.waitForTimeout(100);assert.equal(await page.locator('#export-passes').isDisabled(),false,'Cancelled save dialog resets button');
 await page.locator('#export-passes').click();await page.waitForFunction(()=>document.getElementById('activity-log').textContent.includes('C:/exports/shot.zip'));
 assert.equal(await page.locator('#export-passes').isDisabled(),false);
 await page.evaluate(()=>document.getElementById('toasts').replaceChildren());await page.waitForTimeout(750);await page.screenshot({path:path.join(root,'test-artifacts/red-preview.png')});
 for(const size of [{width:1080,height:740},{width:1920,height:1080}]){
  await page.setViewportSize(size);await page.waitForTimeout(200);
  assert.ok(await page.locator('#export-passes').evaluate(el=>el.getBoundingClientRect().bottom<=innerHeight));
  await page.screenshot({path:path.join(root,`test-artifacts/red-preview-${size.width}.png`)});
  await page.locator('#new-clip').click();assert.equal(await page.evaluate(()=>studio.getState().screen),'setup');
  assert.ok(await page.locator('#generate').evaluate(el=>el.getBoundingClientRect().bottom<=innerHeight));
  assert.ok(await page.locator('#dropzone').evaluate(el=>el.getBoundingClientRect().height>=200));
  await page.waitForTimeout(750);await page.screenshot({path:path.join(root,`test-artifacts/red-setup-${size.width}.png`)});
  await page.locator('#resume-preview').click();
 }
 await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await page.locator('.ambient').first().evaluate(el=>getComputedStyle(el).display),'none');
 assert.deepEqual(errors,[]);await browser.close();console.log('UI PASS: setup, logo, settings, accurate monotonic progress, cancellation, preview, 8 maps, save-dialog cancel/success, responsive layouts and reduced motion.');
})().catch(e=>{console.error(e);process.exit(1)});
