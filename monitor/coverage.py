"""Static source audit combined with the latest actual collection result."""

def registry_rows(pubs, diagnostics=()):
    latest = {r['id']: r for r in diagnostics}
    rows=[]
    for pub in pubs:
        row={'Паб':pub['name'],'Округ':pub['district'],'Адрес':pub['address'],
             'Сайт':pub.get('website',''),'Подтверждение':pub.get('registry_status','Требует подтверждения'),
             'Источников':len(pub['sources']),'Примечание':pub.get('registry_note',''),
             'Источник адреса':pub.get('discovery_url',pub.get('website',''))}
        for kind,label in [('food','Горячее'),('beer','Пиво')]:
            c=pub.get('coverage',{}).get(kind,{})
            row[label]=c.get('status','Не проверено')
            row['Причина: '+label]=c.get('reason','Требуется проверка источника')
            row['Проверено: '+label]=c.get('checked_on','')
            row['Меню: '+label]=c.get('evidence_url','')
            sources=[s for s in pub['sources'] if s['kind']==kind and s.get('enabled',True)]
            checks=[latest.get(s['id'],{}) for s in sources]
            errors=[r for r in checks if r.get('status') in {'error','review','partial'}]
            if errors:
                row[label]='Ошибка обновления' if all(r.get('status') in {'error','review'} for r in checks) else 'Есть ограничения'
                row['Причина: '+label]='; '.join(r.get('message','') for r in errors)
            elif sources and all(r.get('status')=='ok' for r in checks):
                row[label]='Цены получены'
            elif sources:
                row[label]='Подключено, нужен запуск'
        rows.append(row)
    return rows
