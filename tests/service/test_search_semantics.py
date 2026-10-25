"""Business searches must not match hidden UUIDs or storage metadata."""
from itertools import count
from types import SimpleNamespace
import pytest
from docflow.service.repository import ServiceStore

@pytest.fixture
def records(tmp_path,monkeypatch):
    sequence=count()
    monkeypatch.setattr("docflow.service.repository.uuid4",lambda:SimpleNamespace(hex=f"deadbeef{next(sequence):024x}"))
    store=ServiceStore(tmp_path/"project")
    client=store.save_client({"name":"Учебная мастерская","email":"contact@example.test","phone":"+70000000000","notes":"Контактная заметка"})
    equipment=store.save_equipment({"number":"DEVICE-900","model":"Учебный насос","manufacturer":"Пример","serial":"SERIAL-ABC","owner_id":client,"identifiers":"Инвентарный знак"})
    repair=store.create_repair(equipment,"REPAIR-101","Проверочная течь")
    store.save_item(repair,{"kind":"work","name":"Настройка клапана","quantity":"1","price":"123.45","description":"Уникальная проверка"})
    return store,client,equipment,repair

@pytest.mark.parametrize("kind",["clients","equipment","repairs"])
def test_hidden_uuid_fragment_never_finds_unrelated_business_record(records,kind):
    store,*_=records
    assert getattr(store,kind)(query="deadbeef")==[]

@pytest.mark.parametrize("kind,queries",[
    ("clients",["МАСТЕРСКАЯ","contact@example.test","+70000000000","Контактная заметка"]),
    ("equipment",["DEVICE-900","НАСОС","SERIAL-ABC","мастерская","Инвентарный знак"]),
    ("repairs",["REPAIR-101","DEVICE-900","НАСОС","мастерская","Проверочная течь","Настройка клапана","Уникальная проверка","Принято"]),
])
def test_user_business_fields_remain_searchable(records,kind,queries):
    store,*_=records
    for query in queries:
        assert len(getattr(store,kind)(query=query))==1,(kind,query)
