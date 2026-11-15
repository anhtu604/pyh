"""Behavior contracts for channel setup, truthful metrics, and approved publishing."""
import pytest

from tests.ui import test_factory_app as workshop


@pytest.fixture
def run_channel_js(monkeypatch):
    extract = workshop._extract_dashboard_scripts

    def scripts():
        result = extract()
        result[0] = 'const channelOriginalGetId = document.getElementById.bind(document); document.getElementById = id => document.querySelector(\'[id=\"\'+id+\'\"]\') || channelOriginalGetId(id);\n' + result[0]
        result[0] += "\nwsNormalizeWorkState.channel = {renderChannelSection, setupChannelCards, loadChannelConnections, renderChannelPublish, renderChannelReceipt, channelMetricValues, channelPublishAllowed};"
        return result

    monkeypatch.setattr(workshop, '_extract_dashboard_scripts', scripts)
    return workshop._run_workshop_js


def test_setup_credentials_handlers_clear_on_success_without_storage(run_channel_js):
    run_channel_js(r'''
const {pyh, doc, setFetchHandler, localStorage} = ctx;
const ch = pyh.wsNormalizeWorkState.channel;
const assert = (v,m) => {if(!v)throw Error(m)};
const calls=[];
const stored=[]; const originalStore=localStorage.setItem; localStorage.setItem=(k,v)=>{stored.push([k,v]);originalStore(k,v);};
setFetchHandler((url, opts) => {calls.push([url,opts && JSON.parse(opts.body)]);return {ok:true,json:async()=>({youtube:{},tiktok:{}})};});
ch.setupChannelCards();
const yt=doc.getElementById('ch-config-youtube'), tt=doc.getElementById('ch-config-tiktok');
yt.querySelector('[name=credentials_json]').value='secret-desktop-json';
await yt.onsubmit({preventDefault(){}});
assert(calls.some(([u,b])=>u==='/api/channel/configure' && b.platform==='youtube' && b.credentials_json==='secret-desktop-json'),'YouTube JSON submitted');
assert(yt.querySelector('[name=credentials_json]').value==='','YouTube credentials cleared');
tt.querySelector('[name=client_id]').value='client'; tt.querySelector('[name=client_secret]').value='secret-key';
await tt.onsubmit({preventDefault(){}});
assert(calls.some(([u,b])=>u==='/api/channel/configure' && b.platform==='tiktok' && b.client_secret==='secret-key'),'TikTok credentials submitted');
assert(tt.querySelector('[name=client_secret]').value==='','TikTok secret cleared');
tt.querySelector('[name=client_secret]').value='typing';
await ch.loadChannelConnections(); ch.setupChannelCards();
assert(tt.querySelector('[name=client_secret]').value==='typing','refresh preserves typing');
assert(!JSON.stringify(stored).includes('secret-key'),'secret not persisted');
''')


def test_connection_shows_explicit_google_link_without_popup(run_channel_js):
    run_channel_js(r'''
const {pyh,doc,setFetchHandler}=ctx,ch=pyh.wsNormalizeWorkState.channel;
const assert=(v,m)=>{if(!v)throw Error(m)};
setFetchHandler((url,opts)=>({ok:true,json:async()=>url.endsWith('/connect') ? {authorization_url:'https://accounts.google.com/o/oauth2/v2/auth?state=test'} : {youtube:{configured:true,connected:false},tiktok:{}}}));
ch.setupChannelCards();
assert(doc.getElementById('ch-auth-youtube').hidden,'authorization link initially hidden');
await doc.getElementById('ch-connect-youtube').onclick();
const link=doc.getElementById('ch-auth-youtube');
assert(!link.hidden && link.href.startsWith('https://accounts.google.com/'),'explicit usable Google authorization link');
assert(doc.getElementById('ch-auth-help-youtube').textContent.includes('đăng nhập'),'login instructions visible');
setFetchHandler(()=>({ok:true,json:async()=>({youtube:{connected:true,account_title:'Verified channel',can_sync:true},tiktok:{}})}));
await ch.loadChannelConnections();
assert(link.hidden,'consumed authorization link hidden after connection');
assert(!doc.getElementById('ch-sync-youtube').disabled,'sync available after connection');
''')


def test_imported_metrics_and_unknown_values_are_truthful(run_channel_js):
    run_channel_js(r'''
const {pyh,doc}=ctx, ch=pyh.wsNormalizeWorkState.channel;
const assert=(v,m)=>{if(!v)throw Error(m)};
ch.renderChannelSection({connected:false,data_available:false,analysis_ready:false,analysis_reason:'Thiếu dữ liệu'});
assert(doc.getElementById('btn-ch-analyze').disabled,'no data disables analysis');
assert(doc.getElementById('channel-body').textContent.includes('Chưa có số liệu'),'empty state');
ch.renderChannelSection({connected:false,data_available:true,analysis_ready:true,sources:['csv'],videos_count:1,total_views:null,videos:[{title_used:'Imported',views:null}]});
assert(doc.getElementById('channel-status').textContent.includes('chưa kết nối tài khoản'),'import is not OAuth');
assert(doc.getElementById('channel-body').textContent.includes('Imported'),'imported data rendered');
assert(doc.getElementById('channel-body').textContent.includes('CSV đã nhập'),'import source labeled');
assert(doc.getElementById('channel-body').textContent.includes('chưa có số liệu'),'unknown remains unknown');
assert(!doc.getElementById('channel-body').textContent.includes('0 lượt xem'),'unknown not zero');
assert(!doc.getElementById('btn-ch-analyze').disabled,'usable imported data enables analysis');
const blank=ch.channelMetricValues(()=>''), zero=ch.channelMetricValues(k=>k==='views'?'0':'');
assert(!('views' in blank) && !('ctr_pct' in blank),'blank metrics omitted');
assert(zero.views===0,'observed zero retained');
ch.renderChannelSection({data_available:false,analysis_ready:false,insights_stale:true,historical_insights:{summary:'Outdated report'}});
assert(doc.getElementById('channel-body').textContent.includes('cần phân tích lại'),'stale empty state asks reanalysis');
assert(!doc.getElementById('channel-body').textContent.includes('Outdated report'),'stale report never current');
''')


def test_publish_requires_preview_consents_and_exact_account(run_channel_js):
    run_channel_js(r'''
const {pyh,doc,setFetchHandler}=ctx,ch=pyh.wsNormalizeWorkState.channel;
const assert=(v,m)=>{if(!v)throw Error(m)};
pyh.setState({state:{projects:[{slug:'approved',state:'packaged'},{slug:'draft',state:'draft'}]}});
ch.renderChannelPublish();
assert(!doc.getElementById('ch-p-slug').innerHTML.includes('value="draft"'),'draft never offered');
doc.getElementById('ch-p-slug').value='approved';doc.getElementById('ch-p-platform').value='tiktok';doc.getElementById('ch-p-clip').value='CL01';doc.getElementById('ch-p-title').value='0';
assert(!ch.channelPublishAllowed(),'no preview cannot publish');
const calls=[];
setFetchHandler((url,opts)=>{const b=opts&&JSON.parse(opts.body);calls.push([url,b]);return {ok:true,json:async()=>url.endsWith('publish-preview')?{platform:'tiktok',slug:'approved',revision:'r1',clip_id:'CL01',sha256:'abc',title:'Approved title',caption:'Approved caption',gates_current:true,account:{id:'acct',name:'Doctor'},privacy_options:['SELF_ONLY']}:{status:'pending',receipt_id:'receipt'}};});
await doc.getElementById('ch-preview').onclick();
assert(doc.getElementById('ch-preview-body').textContent.includes('Doctor'),'preview shows actual account');
assert(!ch.channelPublishAllowed(),'consent starts unchecked');
doc.getElementById('ch-privacy').value='SELF_ONLY';doc.getElementById('ch-confirm').checked=true;doc.getElementById('ch-music').checked=true;doc.getElementById('ch-noncommercial').checked=true;
assert(ch.channelPublishAllowed(),'all explicit consents allow publish');
await doc.getElementById('ch-send').onclick();
const body=calls.find(([u])=>u==='/api/channel/publish')[1];
assert(body.expected_account_id==='acct' && body.expected_revision==='r1' && body.expected_sha256==='abc' && body.confirmed && body.music_usage_confirmed && body.noncommercial_confirmed,'consents/account sent');
assert(body.privacy==='SELF_ONLY','selected provider privacy sent');
assert(Object.keys(body).sort().join(',')===['platform','slug','clip_id','title_index','privacy','expected_account_id','expected_revision','expected_sha256','confirmed','music_usage_confirmed','noncommercial_confirmed'].sort().join(','),'exact allowed TikTok payload');
assert(doc.getElementById('ch-receipt').textContent.includes('Đang chờ'),'pending is not published');
assert(!doc.getElementById('ch-check').hidden,'explicit status check offered');
assert(!ch.channelPublishAllowed(),'successful request clears preview, no duplicate upload');
assert(calls.filter(([u])=>u==='/api/channel/publish').length===1,'one upload only');
''')


def test_selection_changes_invalidate_preview_and_empty_approved_state(run_channel_js):
    run_channel_js(r'''
const {pyh,doc}=ctx,ch=pyh.wsNormalizeWorkState.channel;
const assert=(v,m)=>{if(!v)throw Error(m)};
pyh.setState({state:{projects:[]}});ch.renderChannelPublish();
assert(doc.getElementById('ch-p-empty').textContent.includes('Chưa có gói'),'empty approved packages');
assert(doc.getElementById('ch-preview').disabled,'no project cannot preview');
doc.getElementById('ch-preview-body').innerHTML='<input id="ch-confirm" type="checkbox">';
doc.getElementById('ch-confirm').checked=true;
doc.getElementById('ch-p-platform').onchange();
assert(doc.getElementById('ch-preview-body').innerHTML==='','selection clears consent display');
assert(doc.getElementById('ch-send').disabled,'selection invalidates publish');
''')


def test_browser_login_progress_capabilities_and_poll_failure(run_channel_js):
    run_channel_js(r'''
const {pyh,doc,setFetchHandler}=ctx,ch=pyh.wsNormalizeWorkState.channel;
const assert=(v,m)=>{if(!v)throw Error(m)};
for(let i=0;i<30;i++) await Promise.resolve();
let status='idle',broken=false;const calls=[];
setFetchHandler((url,opts)=>{calls.push(url);if(url.endsWith('browser-status'))return {ok:!broken,json:async()=>({installed:true,status})};if(url.endsWith('browser-login')){status='logging_in';return {ok:true,json:async()=>({installed:true,status})};}return {ok:true,json:async()=>({youtube:{connected:true,account_title:'Protect Your Health',can_sync:true},tiktok:{connected:true,connection_method:'browser_session',account_title:'TikTok · UID 123',can_sync:false}})};});
ch.setupChannelCards();await ch.loadChannelConnections();
assert(doc.getElementById('ch-browser-install').hidden,'installed tool needs no install action');
await doc.getElementById('ch-browser-login').onclick();
assert(calls.includes('/api/channel/browser-login'),'login explicitly requested');
assert(doc.getElementById('ch-browser-login').disabled,'active job disables login');
assert(doc.getElementById('ch-browser-status').textContent.includes('Đang chờ'),'honest progress');
assert(doc.getElementById('ch-sync-tiktok').disabled,'browser session cannot sync');
assert(doc.getElementById('ch-account-tiktok').textContent.includes('UID 123'),'UID is session identity');
status='connected';await ch.loadChannelConnections();
assert(!doc.getElementById('ch-browser-login').disabled,'completed job allows reconnect');
broken=true;await ch.loadChannelConnections();
assert(doc.getElementById('ch-browser-status').textContent.includes('Chưa đọc được'),'poll failure visible');
broken=false;await ch.loadChannelConnections();
setFetchHandler((url)=>({ok:!url.endsWith('browser-login'),json:async()=>url.endsWith('browser-status') ? {installed:true,status:'idle'} : {error:'Không mở được trình duyệt'}}));
await doc.getElementById('ch-browser-login').onclick();
assert(doc.getElementById('ch-browser-status').textContent.includes('Chưa thực hiện được'),'start failure remains visible after refresh');
''')


def test_browser_preview_privacy_and_pending_receipt_are_truthful(run_channel_js):
    run_channel_js(r'''
const {pyh,doc,setFetchHandler}=ctx,ch=pyh.wsNormalizeWorkState.channel;
const assert=(v,m)=>{if(!v)throw Error(m)};
pyh.setState({state:{projects:[{slug:'approved',state:'packaged'}]}});ch.renderChannelPublish();
doc.getElementById('ch-p-slug').value='approved';doc.getElementById('ch-p-platform').value='tiktok';doc.getElementById('ch-p-clip').value='CL01';
setFetchHandler(()=>({ok:true,json:async()=>({platform:'tiktok',connection_method:'browser_session',revision:'r1',sha256:'abc',account:{id:'uid',name:'TikTok · UID 123'},gates_current:true,privacy_options:['private','public']})}));
await doc.getElementById('ch-preview').onclick();
assert(doc.getElementById('ch-privacy').innerHTML.includes('value="public"'),'public only offered by preview');
assert(!ch.channelPublishAllowed(),'privacy and consent remain explicit');
ch.renderChannelReceipt({status:'pending_verification',receipt_id:'sent'});
assert(doc.getElementById('ch-receipt').textContent.includes('Đã gửi, chờ xác minh trên TikTok'),'accepted is not confirmed posted');
assert(!doc.getElementById('ch-check').hidden,'reconciliation status available');
ch.renderChannelReceipt({status:'posted',receipt_id:'yt',thumbnail_status:'failed'});
assert(doc.getElementById('ch-receipt').textContent.includes('video đã đăng, không đăng lại video'),'thumbnail failure keeps video posted');
assert(doc.getElementById('ch-check').hidden,'no reupload action');
''')
