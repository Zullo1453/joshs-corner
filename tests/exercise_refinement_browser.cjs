/* Fresh exercise_browser_server.py fixture required; no live data is accessed. */
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const {expect}=require('playwright/test');
let browser;
(async()=>{
 browser=await chromium.launch({channel:'chrome',headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:950}}),page=await context.newPage();
 const base='http://127.0.0.1:5012',errors=[];
 const watch=p=>{p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>{if(m.type()==='error')errors.push(m.text());});p.on('response',r=>{if(r.status()>=400)errors.push(`${r.status()} ${r.url()}`);});};watch(page);
 const go=async path=>{await page.goto(base+path);await page.waitForLoadState('load');};
 const click=async locator=>{await locator.click();await page.waitForLoadState('load');};
 const overflow=async p=>assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'overflow '+p.url());
 const aligned=async p=>{const f=p.locator('.exercise-run-form'),a=await f.locator('[name=route_id]').boundingBox(),b=await f.locator('[name=new_route]').boundingBox();assert(Math.abs(a.y-b.y)<2,'route fields not aligned');};
 await go('/gym/history?kind=runs');
 const title=await page.getByRole('heading',{name:'No runs logged yet'}).boundingBox(),action=await page.getByRole('link',{name:'Log a run',exact:true}).boundingBox();assert(action.y>=title.y+title.height+5,'empty state overlap');
 await page.screenshot({path:'instance/refinement-empty-history.png'});
 await go('/gym/runs');await aligned(page);
 await page.screenshot({path:'instance/refinement-run-form.png',fullPage:true});
 await go('/gym');await click(page.getByRole('button',{name:'Start strength workout'}));
 await page.locator('#today-exercise').selectOption('1');await click(page.getByRole('button',{name:'Add to workout'}));
 assert(page.url().includes('#exercise-'));
 const firstForm=page.locator('.gym-new-set').first();await firstForm.locator('[name=weight_kg]').fill('22.5');await firstForm.locator('[name=reps]').fill('8');await click(firstForm.getByRole('button',{name:'Add set',exact:true}));
 for(let i=0;i<5;i++)await click(page.getByRole('button',{name:'Add same set',exact:true}));
 await expect(page.locator('.gym-set-row')).toHaveCount(6);
 assert(page.url().includes('#set-entry-'));
 assert(await page.evaluate(()=>scrollY>100),'adding sets jumped to top');
 await expect(page.locator('.gym-new-set [name=weight_kg]')).toBeInViewport();
 await page.locator('#today-exercise').selectOption('2');await click(page.getByRole('button',{name:'Add to workout'}));
 await expect(page.locator('.gym-workout-card').last().locator('h2')).toBeInViewport();
 assert(await page.evaluate(()=>scrollY>100),'new exercise was not brought into view');
 // Create and use a real duration-only exercise through the UI.
 await go('/gym/exercises');const add=page.locator('form').filter({has:page.locator('#exercise-name')});
 await add.locator('[name=name]').fill('Fictional Plank');await add.locator('[name=body_part]').selectOption('Core');await add.locator('[name=tracking_type]').selectOption('timed');await click(add.getByRole('button',{name:'Add exercise',exact:true}));
 await go('/gym');await page.locator('#today-exercise').selectOption({label:'Fictional Plank'});await click(page.getByRole('button',{name:'Add to workout'}));
 const plank=page.locator('.gym-workout-card').filter({has:page.getByRole('heading',{name:'Fictional Plank',exact:true})});
 await expect(plank.locator('[name=weight_kg]')).toHaveCount(0);
 await plank.locator('.gym-new-set [name=duration]').fill('1:30');await click(plank.getByRole('button',{name:'Add set',exact:true}));
 await click(plank.getByRole('button',{name:'Add same set',exact:true}));
 await expect(plank.locator('.gym-set-row')).toHaveCount(2);await expect(plank.locator('header')).toContainText('3:00');
 await click(plank.getByRole('link',{name:'Fictional Plank',exact:true}));
 const timedPath=new URL(page.url()).pathname;
 await expect(page.getByRole('heading',{name:'Longest hold progression'})).toBeVisible();await expect(page.locator('.gym-chart svg')).toHaveCount(2);
 await page.screenshot({path:'instance/refinement-timed-desktop.png',fullPage:true});
 const log=async(day,time,km='5')=>{await go('/gym/runs');const f=page.locator('.exercise-run-form');if(day==='2026-08-12')await f.locator('[name=new_route]').fill('Fictional Fixed Course');else{await f.locator('[name=route_id]').selectOption('1');await expect(f.locator('[name=distance_km]')).toHaveValue('5');}await f.locator('[name=run_date]').fill(day);await f.locator('[name=distance_km]').fill(km);await f.locator('[name=duration]').fill(time);await click(f.getByRole('button',{name:'Save run',exact:true}));};
 await log('2026-08-12','30:00');await log('2026-08-26','28:00');await log('2026-09-02','25:00');await log('2026-09-02','15:00','3');
 await go('/gym/runs');await click(page.getByRole('button',{name:'View route progress'}));
 await expect(page.getByRole('heading',{name:'Completion time over time'})).toBeVisible();
 await expect(page.locator('.exercise-metrics').first()).toContainText('5:00 quicker');
 await expect(page.locator('.gym-chart[data-metric=elapsed] circle')).toHaveCount(3);
 await expect(page.getByText('1 run(s) outside this distance range excluded from the comparison.',{exact:true})).toBeVisible();
 await page.screenshot({path:'instance/refinement-route-desktop.png',fullPage:true});
 for(const width of [320,375,390,430]){
   const mobile=await browser.newContext({viewport:{width,height:900},isMobile:true,hasTouch:true}),p=await mobile.newPage();watch(p);
   for(const target of ['/gym','/gym/exercises',timedPath,'/gym/runs','/gym/runs/routes/1','/gym/history','/gym/history?kind=runs']){await p.goto(base+target);await p.waitForLoadState('load');await overflow(p);}
   await p.goto(base+'/gym');const timed=p.locator('.gym-workout-card').filter({has:p.getByRole('heading',{name:'Fictional Plank',exact:true})});
   await timed.getByRole('button',{name:'Add same set',exact:true}).tap();await p.waitForLoadState('load');await expect(timed.locator('.gym-new-set [name=duration]')).toBeInViewport();assert(await p.evaluate(()=>scrollY>100));
   await p.goto(base+'/gym/runs/routes/1');await p.locator('.gym-chart[data-metric=elapsed] circle').first().tap();await expect(p.locator('.gym-chart[data-metric=elapsed] .gym-chart-detail')).toContainText('30:00');
   await p.screenshot({path:`instance/refinement-route-${width}.png`,fullPage:true});
   await p.goto(base+'/gym/runs');await overflow(p);await p.screenshot({path:`instance/refinement-runs-${width}.png`,fullPage:true});await mobile.close();
 }
 assert.deepEqual(errors,[]);console.log(JSON.stringify({scrollTargets:true,repeatWeightedAndTimed:true,emptyOverlap:false,runAlignment:true,routeProgress:true,mobile:[320,375,390,430],consoleErrors:0}));
 await browser.close();
})().catch(async error=>{console.error(error);if(browser)await browser.close();process.exitCode=1;});
