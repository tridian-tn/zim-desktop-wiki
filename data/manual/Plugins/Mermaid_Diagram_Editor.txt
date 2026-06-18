Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.6
Creation-Date: 2024-05-14T08:00:00+03:00

====== Mermaid Diagram Editor ======

The Mermaid diagram editor allows you to insert and edit diagrams based on the Mermaid language. Mermaid uses a basic script language to define diagrams. This plugin adds a dialog where one can define a diagram in this script. The dialog shows a preview of the rendered diagram and when the diagram is finished it can be inserted in a zim page as an image. You can always edit it later again by selecting "Edit Diagram" from the context menu (right-mouse-click on the diagram will show the context menu).

**Dependencies:** This plugin requires ''mmdc'' to be installed and available in the system path.

To install the "mmdc" tool use ''npm'':

'''
$ npm install -g @mermaid-js/mermaid-cli
'''


===== Example =====

For example a diagram like:

{{./erd.png}}

Can be created by entering the following definition in the dialog:

'''
erDiagram
	CUSTOMER ||--o{ ORDER : places
	ORDER ||--|{ LINE-ITEM : contains
	CUSTOMER }|..|{ DELIVERY-ADDRESS : uses
'''

==== Another example ====

{{./gantt.png}}

'''
gantt
	title A Gantt Diagram
	dateFormat YYYY-MM-DD
	section Section
		A task          :a1, 2014-01-01, 30d
		Another task    :after a1, 20d
	section Another
		Task in Another :2014-01-12, 12d
		another task    :24d
'''


More info can be found at at:

* https://github.com/mermaid-js/mermaid-cli/
* https://mermaid.js.org/
