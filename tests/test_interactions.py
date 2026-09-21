from browser import run
from checks.interactions import check_interactions

from conftest import fixture_path


def msgs(rep):
    return [f.message for f in rep.findings if f.check == "interactions"]


def test_clean_interactions_have_no_findings():
    rep = run(fixture_path("interactions_clean.html"), [check_interactions], max_pages=1)
    assert rep.pages
    assert msgs(rep) == [], msgs(rep)


def test_interaction_bugs_are_found():
    rep = run(fixture_path("interactions_bad.html"), [check_interactions], max_pages=1)
    m = msgs(rep)
    assert any("Мёртвая кнопка" in x and "не реагирует" in x for x in m), m
    assert any("Отключена через aria" in x and "всё равно реагирует" in x for x in m), m
    assert any("выглядит кликабельным" in x for x in m), m
    assert any("Битый якорь" in x for x in m), m
    assert any("Ссылка-заглушка" in x for x in m), m
    assert any("Форма отправляется с пустыми" in x for x in m), m
    assert any("Двойной клик" in x for x in m), m
    assert any("перекрыта" in x for x in m), m
    # рабочая кнопка не должна попадать в отчёт
    assert not any("Рабочая кнопка" in x for x in m), m
