import os
import pandas as pd


def frame(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df['checked_at'] = pd.to_datetime(df['checked_at'],utc=True)
    df['age_hours'] = (pd.Timestamp.now(tz='UTC')-df['checked_at']).dt.total_seconds()/3600
    df['fresh'] = (df['age_hours'] <= float(os.getenv('STALE_HOURS','48'))) & (df['source_status']=='ok') & (df['snapshot_status']=='ok')
    df['freshness'] = df['fresh'].map({True:'Проверено',False:'Требует проверки'})
    df['checked_msk'] = df['checked_at'].dt.tz_convert('Europe/Moscow').dt.strftime('%d.%m.%Y %H:%M')
    return df


def comparable_beer(df):
    """One observed serving per exact pub/product/type; no double-counted small pints."""
    if df.empty:
        return df
    b = df[(df['category']=='Пиво') & df['volume_ml'].notna() & df['fresh']].copy()
    b['distance_500'] = (b['volume_ml']-500).abs()
    return b.sort_values(['distance_500','volume_ml'],ascending=[True,False]).drop_duplicates(
        ['pub_id','name','serving_type','alcohol_free'])


def describe(df):
    if df.empty:
        return 'Пока нет проверенных цен. Запустите сбор на вкладке «Источники».'
    fresh = df[df['fresh']]
    lines = [f"В выборке {df['pub'].nunique()} заведений и {len(df)} вариантов позиций.",
             f"Свежих наблюдений: {len(fresh)}. Требуют проверки: {len(df)-len(fresh)}."]
    if fresh.empty:
        return '\n\n'.join(lines+['Сравнение цен приостановлено: нет свежих успешных проверок.'])
    changes = fresh[fresh['change_rub'].notna()]
    if changes.empty:
        lines.append('Это базовый замер: для динамики нужен второй успешный сбор.')
    else:
        up,down = (changes['change_rub']>0).sum(),(changes['change_rub']<0).sum()
        lines.append(f'Относительно предыдущего полного снимка: {up} повышений, {down} снижений, {len(changes)-up-down} без изменений.')
    beer = comparable_beer(fresh)
    if not beer.empty:
        lines.append(f"Медиана пива в пересчёте на 0,5 л: {beer['price_500ml'].median():.0f} ₽. "
                     'Это расчёт по выбранному ассортименту; объёмы и типы пива различаются.')
    lines.append('Цены опубликованы на сайтах. Дата проверки не доказывает дату обновления меню; фактическое наличие не подтверждено.')
    return '\n\n'.join(lines)
