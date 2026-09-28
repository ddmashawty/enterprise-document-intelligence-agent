"""参考实现：抓取华南师范大学硕士招生专业目录（ASP.NET WebForms 回发 + 分页）。

目标：https://yanzhao.scnu.edu.cn/Master/Zsml_View.aspx
流程：GET 拿 __VIEWSTATE/__EVENTVALIDATION → POST 选院系 drpYx（__EVENTTARGET=drpYx）
      → 按 lnkPage 链接翻页（__EVENTTARGET=grid 的 Page$N）→ 另 POST drpXxfs=2 取非全日制。
礼貌抓取：每次请求间隔 4 秒。输出 HTML 到当前目录（文件名见下）。
用法：python scripts/scnu_zsml.py 019 041 046
注意：年份下拉目前默认 2026；2027 目录上线后需要额外设置年份下拉的值。
打包时未改动代码，只加了本说明。新 crawler 里应把它改写成 SCNU 适配器（见 CURSOR_PROMPT.md）。
"""
import requests,time,sys
from bs4 import BeautifulSoup
URL='https://yanzhao.scnu.edu.cn/Master/Zsml_View.aspx'
S=requests.Session(); S.headers['User-Agent']='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'
def form(soup):
    d={}
    for i in soup.find_all('input'):
        if i.get('name') and i.get('type','text') in ('hidden','text'): d[i['name']]=i.get('value','')
    for s in soup.find_all('select'):
        o=s.find('option',selected=True) or s.find('option')
        d[s['name']]=o.get('value','') if o else ''
    return d
r=S.get(URL,timeout=60); soup=BeautifulSoup(r.text,'lxml')
for yx in sys.argv[1:]:
    time.sleep(4)
    d=form(soup); d['ctl00$contentParent$drpYx']=yx; d['ctl00$contentParent$drpZy']=''; d['ctl00$contentParent$drpZylx']=''
    d['__EVENTTARGET']='ctl00$contentParent$drpYx'; d['__EVENTARGUMENT']=''
    r2=S.post(URL,data=d,timeout=60); s2=BeautifulSoup(r2.text,'lxml')
    pages=[r2.text]
    # pagination
    while True:
        nxt=[a for a in s2.find_all('a') if 'lnkPage' in (a.get('href') or '') and a.get_text(strip=True)==str(len(pages)+1)]
        if not nxt: break
        time.sleep(4)
        tgt=nxt[0]['href'].split("'")[1]
        d=form(s2); d['__EVENTTARGET']=tgt; d['__EVENTARGUMENT']=''
        r3=S.post(URL,data=d,timeout=60); s2=BeautifulSoup(r3.text,'lxml'); pages.append(r3.text)
    for i,p in enumerate(pages):
        fn=f'scnu_2026_招生专业目录_Zsml_View_{yx}_p{i+1}.html'; open(fn,'w',encoding='utf-8').write(p); print(fn,len(p))
    # also 非全日制
    time.sleep(4)
    d=form(BeautifulSoup(pages[0],'lxml')); d['ctl00$contentParent$drpYx']=yx; d['ctl00$contentParent$drpXxfs']='2'; d['__EVENTTARGET']='ctl00$contentParent$drpXxfs'
    r4=S.post(URL,data=d,timeout=60); fn=f'scnu_2026_招生专业目录_Zsml_View_{yx}_非全日制.html'; open(fn,'w',encoding='utf-8').write(r4.text); print(fn,len(r4.text))
