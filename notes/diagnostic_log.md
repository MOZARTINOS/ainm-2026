
# Diagnostic run 2026-03-21 04:15 — v5-git-patched+override

## Round 2: 0% (0/8.0) — supplier_invoice
- Prompt: Nous avons reçu la facture INV-2026-8172 du fournisseur Montagne SARL (nº org. 937826192) de 71150 NOK TTC. Le montant concerne des services de bureau
- Checks: [FFFF]
- API calls: 1, 4xx errors: 0
- Diagnostics: {"supplierInvoices": 0, "vouchers": 1}
  - [main] ok=True s=201 


# Diagnostic run 2026-03-21 04:20 — v5-patched+override

## Round 4: 38% (3.0/8.0) — create_invoice
- Prompt: Opprett ein faktura til kunden Strandvik AS (org.nr 900314183) med tre produktlinjer: Webdesign (9716) til 13450 kr med 25 % MVA, Skylagring (6906) ti
- Checks: [PPFFFF]
- API calls: 2, 4xx errors: 0
- Diagnostics: {"customers": 1, "customer_list": [{"id": 108309980, "name": "Strandvik AS", "org": "900314183"}]}
  - [create_order] ok=True s=201 
  - [create_invoice] ok=True s=201 

## Round 5: 56% (4.5/8.0) — create_travel_expense
- Prompt: Registe uma despesa de viagem para Bruno Silva (bruno.silva@example.org) referente a "Conferência Bodø". A viagem durou 3 dias com ajudas de custo (ta
- Checks: [PFFPPF]
- API calls: 4, 4xx errors: 0
- Diagnostics: {"employees": 2, "employee_list": [{"id": 18226668, "name": "Admin NM", "userType": null}, {"id": 18607375, "name": "Bruno Silva", "userType": null}]}
  - [main] ok=True s=201 
  - [add_cost] ok=True s=201 
  - [add_cost] ok=True s=201 
  - [add_per_diem] ok=True s=201 

## Round 3: 81% (6.5/8.0) — register_payment
- Prompt: Create an order for the customer Brightstone Ltd (org no. 971948981) with the products Data Advisory (4083) at 4050 NOK and Training Session (7105) at
- Checks: [PPPFP]
- API calls: 5, 4xx errors: 2
- Diagnostics: {"customers": 1, "customer_list": [{"id": 108309953, "name": "Brightstone Ltd", "org": "971948981"}]}
  - [create_product] ok=False s=422 Produktnavnet "Data Advisory" er allered
  - [create_product] ok=False s=422 Produktnavnet "Training Session" er alle
  - [create_order] ok=True s=201 
  - [create_invoice] ok=True s=201 
  - [payment] ok=True s=200 

## Round 6: 56% (4.5/8.0) — create_travel_expense
- Prompt: Registe uma despesa de viagem para Bruno Santos (bruno.santos@example.org) referente a "Conferência Drammen". A viagem durou 3 dias com ajudas de cust
- Checks: [PFFPPF]
- API calls: 4, 4xx errors: 0
- Diagnostics: {"employees": 2, "employee_list": [{"id": 18226679, "name": "Admin NM", "userType": null}, {"id": 18607301, "name": "Bruno Santos", "userType": null}]}
  - [main] ok=True s=201 
  - [add_cost] ok=True s=201 
  - [add_cost] ok=True s=201 
  - [add_per_diem] ok=True s=201 


# Diagnostic run 2026-03-21 04:27 — v5-patched

## Round 8: 0% (0/8.0) — supplier_invoice
- Prompt: Recebemos a fatura INV-2026-7230 do fornecedor Solmar Lda (org. nº 973188410) no valor de 7700 NOK com IVA incluído. O montante refere-se a serviços d
- Checks: [FFFF]
- API calls: 1, 4xx errors: 0
- Diagnostics: {"supplierInvoices": 0, "vouchers": 1}
  - [main] ok=True s=201 

## Round 2: 0% (0/8.0) — supplier_invoice
- Prompt: Recebemos a fatura INV-2026-7230 do fornecedor Solmar Lda (org. nº 973188410) no valor de 7700 NOK com IVA incluído. O montante refere-se a serviços d
- Checks: [FFFF]
- API calls: 1, 4xx errors: 0
- Diagnostics: {"supplierInvoices": 0, "vouchers": 1}
  - [main] ok=True s=201 

## Round 7: 0% (0/13.0) — dimension_voucher
- Prompt: Erstellen Sie eine benutzerdefinierte Buchhaltungsdimension "Kostsenter" mit den Werten "Kundeservice" und "Markedsføring". Buchen Sie dann einen Bele
- Checks: [FFFFFF]
- API calls: 5, 4xx errors: 2
- Diagnostics: {"supplierInvoices": 0, "vouchers": 1, "dimensions": 0, "dimension_values": 0}
  - [create_dimension] ok=False s=422 Feltet eksisterer ikke i objektet.
  - [create_dimension] ok=False s=404 
  - [create_dept_as_dimension] ok=True s=201 
  - [create_dept_Kundeservice] ok=True s=201 
  - [create_voucher] ok=True s=201 

## Round 10: 0% (0/8.0) — supplier_invoice
- Prompt: Recebemos a fatura INV-2026-3196 do fornecedor Montanha Lda (org. nº 810189096) no valor de 21350 NOK com IVA incluído. O montante refere-se a serviço
- Checks: [FFFF]
- API calls: 1, 4xx errors: 0
- Diagnostics: {"supplierInvoices": 0, "vouchers": 1}
  - [main] ok=True s=201 


# Diagnostic run 2026-03-21 04:37 — v5-patched+override

## Round 9: 0% (0/8.0) — supplier_invoice
- Prompt: Vi har mottatt faktura INV-2026-8551 fra leverandøren Bergvik AS (org.nr 989568469) på 14850 kr inklusiv MVA. Beløpet gjelder kontortjenester (konto 6
- Checks: [FFFF]
- API calls: 1, 4xx errors: 0
- Diagnostics: {"supplierInvoices": 0, "vouchers": 1}
  - [main] ok=True s=201 

## Round 10: 75% (6.0/8.0) — create_employee
- Prompt: We have a new employee named Ella Harris, born 21. October 1981. Please create them as an employee with email ella.harris@example.org and start date 2
- Checks: [PPPPPFF]
- API calls: 3, 4xx errors: 0
- Diagnostics: {"employees": 2, "employee_list": [{"id": 18226661, "name": "Admin NM", "userType": null}, {"id": 18614215, "name": "Ella Harris", "userType": null}]}
  - [main] ok=True s=201 
  - [grant_entitlements] ok=True s=200 
  - [set_start_date] ok=True s=200 

## Round 2: 0% (0/8.0) — payroll_voucher
- Prompt: Ejecute la nómina de Andrés Romero (andres.romero@example.org) para este mes. El salario base es de 47050 NOK. Añada una bonificación única de 16600 N
- Checks: [FFFF]
- API calls: 1, 4xx errors: 0
- Diagnostics: {"supplierInvoices": 0, "vouchers": 1, "employees": 2, "employee_list": [{"id": 18227768, "name": "Admin NM", "userType": null}, {"id": 18607690, "name": "Andrés Romero", "userType": null}]}
  - [main] ok=True s=201 

## Round 11: 0% (0/8.0) — payroll_voucher
- Prompt: Ejecute la nómina de Andrés Romero (andres.romero@example.org) para este mes. El salario base es de 47050 NOK. Añada una bonificación única de 16600 N
- Checks: [FFFF]
- API calls: 1, 4xx errors: 0
- Diagnostics: {"supplierInvoices": 0, "vouchers": 1, "employees": 2, "employee_list": [{"id": 18227768, "name": "Admin NM", "userType": null}, {"id": 18607690, "name": "Andrés Romero", "userType": null}]}
  - [main] ok=True s=201 

## Round 15: 0% (0/8.0) — supplier_invoice
- Prompt: Wir haben die Rechnung INV-2026-6337 vom Lieferanten Waldstein GmbH (Org.-Nr. 927720523) über 55950 NOK einschließlich MwSt. erhalten. Der Betrag betr
- Checks: [FFFF]
- API calls: 1, 4xx errors: 0
- Diagnostics: {"supplierInvoices": 0, "vouchers": 1}
  - [main] ok=True s=201 


# Diagnostic run 2026-03-21 04:51 — v5+incomingInv

## Round 19: 12% (1.0/8.0) — credit_note
- Prompt: El cliente Viento SL (org. nº 978503071) ha reclamado sobre la factura por "Licencia de software" (25450 NOK sin IVA). Emita una nota de crédito compl
- Checks: [PFFFF]
- API calls: 3, 4xx errors: 0
- Diagnostics: {"customers": 2, "customer_list": [{"id": 108309947, "name": "Brückentor GmbH", "org": "907980634"}, {"id": 108309965, "name": "Viento SL", "org": "978503071"}]}
  - [create_order] ok=True s=201 
  - [create_invoice] ok=True s=201 
  - [main] ok=True s=200 


# Diagnostic run 2026-03-21 04:58 — v5-git-patched+override

## Round 9: 75% (6.0/8.0) — create_employee
- Prompt: Temos um novo funcionário chamado Maria Costa, nascido em 21. July 1990. Crie-o como funcionário com o e-mail maria.costa@example.org e data de início
- Checks: [PPPPPFF]
- API calls: 3, 4xx errors: 0
- Diagnostics: {"employees": 2, "employee_list": [{"id": 18227067, "name": "Admin NM", "userType": null}, {"id": 18615101, "name": "Maria Costa", "userType": null}]}
  - [main] ok=True s=201 
  - [grant_entitlements] ok=True s=200 
  - [set_start_date] ok=True s=200 

## Round 4: 25% (2.0/8.0) — project_invoice
- Prompt: Sett fastpris 203000 kr på prosjektet "Digital transformasjon" for Stormberg AS (org.nr 834028719). Prosjektleder er Hilde Hansen (hilde.hansen@exampl
- Checks: [PFFF]
- API calls: 5, 4xx errors: 0
- Diagnostics: {"employees": 3, "employee_list": [{"id": 18228572, "name": "Admin NM", "userType": null}, {"id": 18607882, "name": "Lucas Santos", "userType": null}, {"id": 18607885, "name": "Hilde Hansen", "userType": null}], "projects": 2}
  - [create_project] ok=True s=201 
  - [create_activity] ok=True s=201 
  - [link_activity] ok=True s=201 
  - [create_order] ok=True s=201 
  - [create_invoice] ok=True s=201 

## Round 23: 0% (0/8.0) — payroll_voucher
- Prompt: Kjør lønn for Lars Berg (lars.berg@example.org) for denne måneden. Grunnlønn er 40850 kr. Legg til en engangsbonus på 14800 kr i tillegg til grunnlønn
- Checks: [FFFF]
- API calls: 1, 4xx errors: 0
- Diagnostics: {"supplierInvoices": 0, "vouchers": 1, "employees": 2, "employee_list": [{"id": 18228447, "name": "Admin NM", "userType": null}, {"id": 18607869, "name": "Lars Berg", "userType": null}]}
  - [main] ok=True s=201 

## Round 12: 75% (6.0/8.0) — create_employee
- Prompt: Me har ein ny tilsett som heiter Turid Kvamme, fødd 31. May 1985. Opprett vedkomande som tilsett med e-post turid.kvamme@example.org og startdato 18. 
- Checks: [PPPPPFF]
- API calls: 3, 4xx errors: 0
- Diagnostics: {"employees": 2, "employee_list": [{"id": 18227296, "name": "Admin NM", "userType": null}, {"id": 18615429, "name": "Turid Kvamme", "userType": null}]}
  - [main] ok=True s=201 
  - [grant_entitlements] ok=True s=200 
  - [set_start_date] ok=True s=200 

## Round 25: 75% (6.0/8.0) — create_employee
- Prompt: Wir haben einen neuen Mitarbeiter namens Anna Schneider, geboren am 6. August 2000. Bitte legen Sie ihn als Mitarbeiter mit der E-Mail anna.schneider@
- Checks: [PPPPPFF]
- API calls: 3, 4xx errors: 0
- Diagnostics: {"employees": 2, "employee_list": [{"id": 18227357, "name": "Admin NM", "userType": null}, {"id": 18615574, "name": "Anna Schneider", "userType": null}]}
  - [main] ok=True s=201 
  - [grant_entitlements] ok=True s=200 
  - [set_start_date] ok=True s=200 

## Round 30: 29% (2.0/7.0) — register_payment
- Prompt: O cliente Estrela Lda (org. nº 977023211) tem uma fatura pendente de 13650 NOK sem IVA por "Design web". Registe o pagamento total desta fatura.
- Checks: [PF]
- API calls: 4, 4xx errors: 0
- Diagnostics: {"customers": 1, "customer_list": [{"id": 108309310, "name": "Estrela Lda", "org": "977023211"}]}
  - [create_product] ok=True s=201 
  - [create_order] ok=True s=201 
  - [create_invoice] ok=True s=201 
  - [payment] ok=True s=200 

