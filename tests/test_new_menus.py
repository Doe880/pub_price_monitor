import pytest
from monitor.menus import parse_dom
from monitor.pdf_menus import parse_pdf
from monitor.coverage import registry_rows


def source(recipe,kind,sections):
    return dict(recipe=recipe,kind=kind,sections=sections)


def test_purkin_pairs_volume_with_price_and_excludes_cider():
    html='''<h2 class="category-title">ПИВО РАЗЛИВНОЕ</h2>
    <div class="drink-item"><h3 class="drink-name">Lager</h3><p class="drink-details">Пиво 5%</p>
    <span class="price-item">0,33л./310₽</span><span class="price-item">0,5л./410₽</span></div>
    <div class="drink-item"><h3 class="drink-name">Apple</h3><p class="drink-details">Сидр</p>
    <span class="price-item">0,5л./550₽</span></div><h2 class="category-title">ВИСКИ</h2>
    <div class="drink-item"><h3 class="drink-name">Whiskey</h3><span class="price-item">40мл./550₽</span></div>'''
    rows,notes=parse_dom(html,source('purkin','beer',['ПИВО РАЗЛИВНОЕ']))
    assert [(x.price,x.volume_ml) for x in rows]==[(310,330),(410,500)]
    assert not notes


def test_4brewers_does_not_mix_side_dishes_with_hot_mains():
    html='''<div class="section">БЛЮДА</div><div class="dish" price="850"><div class="card-title">Стейк</div>
    <div class="card-footer"><div class="text-muted">300 г.</div></div></div>
    <div class="section">Дополнительно к бургерам</div><div class="dish" price="100"><div class="card-title">Сыр</div></div>'''
    rows,_=parse_dom(html,source('4brewers_food','food',['БЛЮДА']))
    assert len(rows)==1 and rows[0].weight_g==300 and rows[0].price==850


def test_bobby_rejects_ambiguous_beer_prices():
    html='''<div class="food-drink"><h4>Lager <strong>300₽ / 450₽</strong></h4><p><em>0,5 л</em></p></div>'''
    with pytest.raises(ValueError,match='число цен'):
        parse_dom(html,source('bobby_beer','beer',[]))


def test_dom_missing_category_cannot_publish_partial_menu_as_complete():
    with pytest.raises(ValueError,match='Не найдены разделы'):
        parse_dom('<html></html>',source('collins','food',['СТЕЙКИ']))


def fake_pdf(monkeypatch,content):
    class Page:
        def extract_text(self,**kwargs):return content
    class Reader:
        def __init__(self,*args):self.pages=[Page()]
    monkeypatch.setattr('monitor.pdf_menus.PdfReader',Reader)


def test_pdf_beer_ignores_cider_and_does_not_infer_unit(monkeypatch):
    content='ПИВО И СИДРЫ\n'+('Меню ' * 20)+'\nLAGER          510 q\nПиво 5%\nAPPLE         490 q\nСИДР\nZERO         390 q\nБАНКА 0,33 Б/А\n'
    fake_pdf(monkeypatch,content)
    rows,_=parse_pdf(b'%PDF',{'kind':'beer'})
    assert len(rows)==2 and all(x.volume_ml is None for x in rows)
    assert rows[1].price==390 and '0,33' in rows[1].portion


def test_pdf_food_keeps_columns_separate_and_suppresses_salads(monkeypatch):
    content='\n'.join(['ГОРЯЧЕЕ'+' '*130+'ЗАКУСКИ', 'СТЕЙК 300г.'+' '*100+'900',
                      'САЛАТЫ','САЛАТ 100г.'+' '*100+'300','БУРГЕРЫ','БУРГЕР 350г.'+' '*100+'700','СОУСЫ'])
    fake_pdf(monkeypatch,content)
    rows,_=parse_pdf(b'%PDF',{'kind':'food'})
    assert [(r.name,r.price) for r in rows]==[('СТЕЙК',900),('БУРГЕР',700)]


def test_registry_latest_error_overrides_static_connected_status():
    pub={'name':'Паб','id':'x','district':'ЦАО','address':'Адрес','sources':[{'id':'x_food','kind':'food'}],
         'coverage':{'food':{'status':'Подключено','reason':'Подключён'},'beer':{'status':'Нужна доработка','reason':'PDF'}}}
    rows=registry_rows([pub],[{'id':'x_food','status':'error','message':'HTTP 503'}])
    assert rows[0]['Горячее']=='Ошибка обновления'
    assert rows[0]['Причина: Горячее']=='HTTP 503'
    assert rows[0]['Пиво']=='Нужна доработка'


def test_tilda_cider_description_is_not_beer():
    from monitor.parsers import parse_tilda_product
    rows,_=parse_tilda_product({'title':'Dickiy Crest Dry','descr':'Сухой сидр','editions':[{'price':'650'}]},'Пиво','beer')
    assert not rows
