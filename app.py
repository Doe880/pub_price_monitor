import os
import pandas as pd
import plotly.express as px
import streamlit as st
from monitor.config import DATA,load_sources
from monitor import storage
from monitor.analytics import frame,describe,comparable_beer
from monitor.collector import collect
from monitor.ai import summarize
from monitor.coverage import registry_rows

st.set_page_config(page_title='Пабометр · Москва',page_icon='📊',layout='wide')
st.markdown('''<style>
.block-container{padding-top:2rem;max-width:1550px}
h1,h2,h3{color:#193b30} [data-testid="stMetric"]{background:#fff;border:1px solid #ded9cc;padding:18px;border-radius:12px}
[data-testid="stMetricValue"]{color:#a65f23} .stTabs [data-baseweb="tab"]{font-size:16px}
</style>''',unsafe_allow_html=True)
st.title('Пабометр · Москва')
st.caption('ЦАО · САО · СВАО  |  Горячие блюда и пиво  |  Цены из официальных меню')

pubs = load_sources()
storage.sync_sources(pubs)
df = frame(storage.current_rows())
diag = pd.DataFrame(storage.diagnostics())

with st.sidebar:
    st.header('Выборка')
    districts = st.multiselect('Округа',['ЦАО','САО','СВАО'],default=['ЦАО','САО','СВАО'])
    available = [p['name'] for p in pubs if p['district'] in districts and p.get('enabled',True)]
    selected_pubs = st.multiselect('Заведения',available,default=available)
    cats = st.multiselect('Категории',['Горячие блюда','Пиво'],default=['Горячие блюда','Пиво'])
    search = st.text_input('Поиск по названию')
    fresh_only = st.checkbox('Только свежие успешные проверки',value=False)
    st.caption('Реестр найденных адресов не гарантирует полный охват всех действующих пабов. Подтверждение адреса и подключение цен показаны отдельно.')
    st.caption('Настройка списка: sources.json. Обновление: вкладка «Источники».')

view = df.copy()
if not view.empty:
    view = view[view['district'].isin(districts)&view['pub'].isin(selected_pubs)&view['category'].isin(cats)]
    if search:
        view = view[view['name'].str.contains(search,case=False,regex=False,na=False)]
    if fresh_only:
        view = view[view['fresh']]

summary_tab,prices_tab,history_tab,events_tab,registry_tab,sources_tab = st.tabs(
    ['Обзор','Цены и сравнение','История','Изменения меню','Пабы с ценами','Источники'])


def table(data,key=None):
    if isinstance(data,list):
        data = pd.DataFrame(data)
    names = {'pub':'Паб','district':'Округ','area':'Район','address':'Адрес','name':'Позиция',
             'note':'Примечание','category':'Категория','subcategory':'Раздел меню','price':'Цена, ₽',
             'portion':'Порция','volume_ml':'Объём, мл','price_500ml':'Расчёт за 0,5 л, ₽',
             'price_basis':'Цена за','serving_type':'Подача','alcohol_free':'Без алкоголя',
             'change_rub':'Изменение, ₽','change_pct':'Изменение, %','previous_price':'Предыдущая цена, ₽',
             'freshness':'Проверка','checked_msk':'Проверено, МСК','source_url':'Официальное меню',
             'old_price':'Было, ₽','new_price':'Стало, ₽','event':'Событие','checked_at':'Дата UTC'}
    st.dataframe(data.rename(columns=names),use_container_width=True,hide_index=True,
                 column_config={'Официальное меню':st.column_config.LinkColumn('Официальное меню',display_text='Открыть')},key=key)


def csv_bytes(data):
    # Protect exported spreadsheets from interpreting names as formulas.
    safe = data.copy()
    for col in safe.select_dtypes(include=['object','string']).columns:
        safe[col] = safe[col].map(lambda x: "'"+x if isinstance(x,str) and x.startswith(('=','+','-','@')) else x)
    return safe.to_csv(index=False,sep=';').encode('utf-8-sig')


with summary_tab:
    scoped = [p for p in pubs if p['district'] in districts and p['name'] in selected_pubs]
    r1,r2,r3 = st.columns(3)
    r1.metric('Адресов в реестре', len(scoped))
    r2.metric('Подключён сбор цен', sum(bool(p['sources']) for p in scoped))
    r3.metric('Без автоматического сбора', sum(not p['sources'] for p in scoped))
    st.caption('Подключение меню не означает успешную текущую проверку. Её результат показан в ценах и диагностике.')
    if view.empty:
        st.info('Нет данных для выбранных фильтров. Для первого замера откройте «Источники» → «Проверить цены сейчас».')
    else:
        fresh = view[view['fresh']]
        a,b,c,d = st.columns(4)
        a.metric('Заведений',view['pub'].nunique())
        b.metric('Позиций с порциями',len(view))
        c.metric('Свежих цен',len(fresh))
        d.metric('Требуют проверки',len(view)-len(fresh))
        st.markdown(describe(view))
        st.caption('Каждый объём пива считается отдельной позицией. Свежесть — успешная проверка не старше '+os.getenv('STALE_HOURS','48')+' часов.')
        chart = fresh.groupby(['pub','category'],as_index=False).size().rename(columns={'size':'count'})
        if not chart.empty:
            fig = px.bar(chart,x='pub',y='count',color='category',barmode='group',
                         color_discrete_map={'Горячие блюда':'#b97638','Пиво':'#285c4a'},
                         labels={'pub':'','count':'Вариантов с ценой','note':'Примечание','category':'Категория'},title='Охват официальных меню')
            fig.update_layout(font_size=16,legend_title_text='')
            st.plotly_chart(fig,use_container_width=True)
        st.subheader('Аналитическая записка')
        st.caption('ИИ получает только выбранные свежие цены и историю. Не используется для придумывания или исправления цен. Запрос к API платный; одинаковая выборка кэшируется.')
        if st.button('Сформировать ИИ-сводку',disabled=not bool(os.getenv('AI_API_KEY'))):
            try:
                with st.spinner('Анализирую выбранные наблюдения…'):
                    st.session_state['ai_result'] = summarize(view)
                    st.session_state['ai_scope'] = (tuple(selected_pubs),tuple(cats),search,tuple(view['check_id'].unique()))
            except Exception as exc:
                st.error(str(exc))
        if not os.getenv('AI_API_KEY'):
            st.info('Для ИИ-сводки заполните AI_API_KEY, AI_BASE_URL и AI_MODEL в .env. Сбор, таблицы, графики и обычная сводка уже работают без API.')
        scope = (tuple(selected_pubs),tuple(cats),search,tuple(view['check_id'].unique()))
        if st.session_state.get('ai_result') and st.session_state.get('ai_scope') == scope:
            st.warning('ИИ-интерпретация: сверяйте выводы с таблицей и первоисточниками.')
            st.markdown(st.session_state['ai_result'])

with prices_tab:
    if view.empty:
        st.info('Нет данных для выбранных фильтров.')
    else:
        st.subheader('Фильтры цен')
        f1, f2, f3 = st.columns(3)
        price_pubs = f1.multiselect(
            'Паб', sorted(view['pub'].dropna().unique().tolist()),
            default=sorted(view['pub'].dropna().unique().tolist()), key='price_pubs')
        filtered = view[view['pub'].isin(price_pubs)].copy()
        price_names = f2.multiselect(
            'Позиция', sorted(filtered['name'].dropna().unique().tolist()),
            default=[], placeholder='Все позиции', key='price_names')
        if price_names:
            filtered = filtered[filtered['name'].isin(price_names)]
        price_portions = f3.multiselect(
            'Порция', sorted(filtered['portion'].dropna().unique().tolist()),
            default=[], placeholder='Все порции', key='price_portions')
        if price_portions:
            filtered = filtered[filtered['portion'].isin(price_portions)]
        chart_type = st.radio('Тип графиков', ['Столбчатый / распределение', 'Линейный'],
                              horizontal=True, key='price_chart_type')
        st.caption('Линейный вид соединяет медианные значения по пабам для наглядного сравнения; '
                   'ось пабов не является временной шкалой и линия не показывает динамику цен.')
        if filtered.empty:
            st.info('По выбранным пабам, позициям и порциям цен не найдено.')
        else:
            cols = ['pub','district','name','category','subcategory','portion','price_basis','serving_type',
                    'alcohol_free','price','price_500ml','note','change_rub','change_pct','checked_msk','freshness','source_url']
            table(filtered[cols], key='prices')
            st.download_button('Скачать таблицу CSV', csv_bytes(filtered[cols]),
                               'pub_prices.csv', 'text/csv')
            st.caption('Пересчёт на 0,5 л нужен для сравнения. Паб может не продавать такую порцию. '
                       '«В меню» не подтверждает наличие сегодня.')
            st.subheader('Сравнение пива')
            beer = comparable_beer(filtered)
            if not beer.empty:
                left, right = st.columns(2)
                serving = left.selectbox('Тип подачи', sorted(beer['serving_type'].unique()))
                free = right.selectbox('Алкоголь', ['Обычное','Безалкогольное'])
                beer = beer[(beer['serving_type'] == serving) &
                            (beer['alcohol_free'] == (free == 'Безалкогольное'))]
                st.caption('Для каждого сорта выбрана порция, ближайшая к 500 мл среди выбранных порций. '
                           'Сорта разных пабов не считаются идентичными.')
                if not beer.empty:
                    if chart_type == 'Линейный':
                        plot_data = beer.groupby('pub', as_index=False)['price_500ml'].median()
                        fig = px.line(plot_data, x='pub', y='price_500ml', markers=True,
                                      labels={'pub':'Паб','price_500ml':'Медианная цена за 0,5 л, ₽'},
                                      title='Медианные цены пива по пабам (не динамика)')
                    else:
                        fig = px.box(beer, x='pub', y='price_500ml', points='all', color='pub',
                                     hover_data=['name','portion','price'],
                                     labels={'pub':'','price_500ml':'Расчёт за 0,5 л, ₽'},
                                     title='Распределение цен по ассортименту')
                    fig.update_layout(showlegend=False, font_size=15)
                    st.plotly_chart(fig, use_container_width=True)
            st.subheader('Сравнение горячих блюд')
            food = filtered[(filtered['category'] == 'Горячие блюда') & filtered['fresh']]
            if not food.empty:
                basis = st.radio('Единица цены', ['порция','100 г'], horizontal=True)
                food = food[food['price_basis'] == basis]
                sections = st.multiselect('Разделы меню', sorted(food['subcategory'].unique()))
                if sections:
                    food = food[food['subcategory'].isin(sections)]
                if not food.empty:
                    if chart_type == 'Линейный':
                        plot_data = food.groupby('pub', as_index=False)['price'].median()
                        fig = px.line(plot_data, x='pub', y='price', markers=True,
                                      labels={'pub':'Паб','price':'Медианная цена, ₽'},
                                      title='Медианные цены горячих блюд по пабам (не динамика)')
                    else:
                        fig = px.box(food, x='pub', y='price', points='all', color='pub',
                                     hover_data=['name','portion'],
                                     labels={'pub':'','price':'Цена, ₽'},
                                     title='Цены выбранных блюд — состав меню различается')
                    fig.update_layout(showlegend=False, font_size=15)
                    st.plotly_chart(fig, use_container_width=True)

with history_tab:
    hist = pd.DataFrame(storage.history_rows())
    if hist.empty:
        st.info('История появится после первого сбора.')
    else:
        hist = hist[hist['pub'].isin(selected_pubs)&hist['district'].isin(districts)&hist['category'].isin(cats)]
        if search:
            hist = hist[hist['name'].str.contains(search,case=False,regex=False)]
        hist['series_key'] = hist['source_id']+':'+hist['item_key']
        opts = hist.drop_duplicates('series_key')
        labels = {r['series_key']:f"{r['pub']} · {r['name']} · {r['portion']} · {r['serving_type']}" for _,r in opts.iterrows()}
        if not opts.empty:
            chosen = st.selectbox('Позиция',list(labels),format_func=lambda k:labels[k])
            h = hist[hist['series_key']==chosen].copy()
            h['time'] = pd.to_datetime(h['checked_at'],utc=True).dt.tz_convert('Europe/Moscow')
            if len(h)<2:
                st.info('Пока один замер. Динамика появится после следующего успешного сбора; прошлые цены не восстанавливаются задним числом.')
            fig = px.line(h,x='time',y='price',markers=True,hover_data=['status'],
                          labels={'time':'Проверено, МСК','price':'Цена, ₽'},title=labels[chosen])
            fig.update_traces(line_color='#285c4a')
            st.plotly_chart(fig,use_container_width=True)
            table(h[['pub','name','portion','price','checked_at','status','source_url']])
            st.download_button('Скачать историю CSV',csv_bytes(h.drop(columns='time')),'price_history.csv','text/csv')
            with st.expander('Текст из меню и подтверждение'):
                st.text(h.iloc[-1]['evidence'])
                st.caption('Исходные ответы сайтов сохраняются в data/snapshots; manifest.json содержит ссылки и SHA-256 файлов.')
        else:
            st.info('Для выбранных фильтров истории нет.')

with events_tab:
    changes = pd.DataFrame(storage.events())
    st.caption('События считаются между полными успешными снимками одного источника. Пропавшая позиция означает только отсутствие в новом меню, а не отсутствие в заведении. Переименование или смена порции создаёт новую позицию.')
    if changes.empty:
        st.info('Изменений пока нет. Первый сбор фиксирует базовый уровень.')
    else:
        changes = changes[changes['pub'].isin(selected_pubs)&changes['district'].isin(districts)&changes['category'].isin(cats)]
        if search:
            changes = changes[changes['name'].str.contains(search,case=False,regex=False)]
        table(changes[['checked_at','pub','name','portion','event','old_price','new_price','source_url']])
        st.download_button('Скачать изменения CSV',csv_bytes(changes),'menu_changes.csv','text/csv')

with registry_tab:
    st.subheader('Реестр · ЦАО, САО, СВАО')
    st.caption('Каталоги используются для поиска адресов. Цены загружаются только из официальных меню. Наличие в реестре не подтверждает, что заведение сейчас работает.')
    registry = pd.DataFrame(registry_rows(pubs, diag.to_dict('records')))
    registry = registry[registry['Округ'].isin(districts)&registry['Паб'].isin(selected_pubs)]
    coverage = st.radio('Подключение меню',['Все адреса','Есть сбор цен','Без сбора цен','Нужна доработка'],horizontal=True)
    if coverage == 'Есть сбор цен':
        registry = registry[registry['Источников']>0]
    elif coverage == 'Без сбора цен':
        registry = registry[registry['Источников']==0]
    elif coverage == 'Нужна доработка':
        registry = registry[(registry['Горячее']=='Нужна доработка') | (registry['Пиво']=='Нужна доработка')]
    st.dataframe(registry,hide_index=True,use_container_width=True,column_config={
        'Сайт':st.column_config.LinkColumn(),'Источник адреса':st.column_config.LinkColumn(),
        'Меню: Горячее':st.column_config.LinkColumn(),'Меню: Пиво':st.column_config.LinkColumn()})
    st.download_button('Скачать реестр CSV',csv_bytes(registry),'pub_registry.csv','text/csv')
    st.info('«Нужна доработка» означает, что поддержка меню ещё не реализована. «Источник недоступен» — результат конкретной попытки, а не доказательство отсутствия цен или закрытия паба. Причины, даты и ссылки указаны отдельно для кухни и пива.')

with sources_tab:
    st.subheader('Официальные источники')
    st.caption('Цены берутся из официальных HTML-меню, публичных каталогов меню и поддержанных PDF. Агрегаторы и поисковые сниппеты не используются. Для каждого неподключённого раздела есть причина во вкладке «Все пабы».')
    registry = pd.DataFrame([{k:p[k] for k in ['name','district','area','address','website','format']} for p in pubs])
    st.dataframe(registry.rename(columns={'name':'Паб','district':'Округ','area':'Район','address':'Адрес','website':'Сайт','format':'Формат'}),
                 hide_index=True,use_container_width=True,column_config={'Сайт':st.column_config.LinkColumn()})
    st.subheader('Обновление')
    selected_ids = [p['id'] for p in pubs if p['name'] in selected_pubs and any(s.get('enabled',True) for s in p['sources'])]
    st.caption(f'Обновятся {len(selected_ids)} выбранных заведений с подключёнными меню. Не имеющие проверенных цен заведения перенесены в архив реестра.')
    if st.button('Проверить цены сейчас',type='primary',disabled=not selected_ids):
        bar = st.progress(0,text='Подготовка…')
        try:
            results = collect(selected_ids,lambda n,total,label:bar.progress(n/max(total,1),text=label))
            st.session_state['collection_result'] = results
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    if 'collection_result' in st.session_state:
        results = st.session_state['collection_result']
        ok = sum(r['status']=='ok' for r in results)
        st.info(f'Последний запуск: {ok} из {len(results)} источников полностью обработаны.')
    st.subheader('Диагностика')
    if not diag.empty:
        display = diag[['pub','district','id','url','status','count','checked_at','last_success','message']].copy()
        display['status'] = display['status'].fillna('не проверен')
        st.dataframe(display.rename(columns={'pub':'Паб','district':'Округ','id':'Источник','url':'Меню',
                     'status':'Статус','count':'Извлечено','checked_at':'Попытка UTC','last_success':'Полный успех UTC','message':'Подробности'}),
                     use_container_width=True,hide_index=True,column_config={'Меню':st.column_config.LinkColumn()})
    st.markdown('**ok** — полный успешный разбор; **partial** — часть строк требует проверки; **review** — подозрительное сокращение меню; **error** — сайт не обработан.')
    st.caption('При ошибках и неполных обновлениях показывается последний полный снимок с предупреждением. Если полного снимка ещё не было, показываются распознанные строки partial. Review не попадает в цены.')
    st.info('Для ежедневной проверки без открытого дэшборда настройте Планировщик заданий Windows по README_RU.md. Расписание в самом чате не создаётся.')
