import xml.etree.ElementTree as ET
import yaml  # pyyaml package
import sys


def collapse_spaces(t):
    lines = t.splitlines()
    out = []
    for ln in lines:
        lst = ln.lstrip()
        if lst != ln:
            lst = " " + lst
        out.append(lst)
    return "\n".join(out)


def extract_text(root):
    output = ""
    for para in root.findall("t"):
        output += para.text + "\n"
    return output


def section_title(elem: ET, level):
    anchor = "{#" + elem.get("anchor") + "}"
    name = elem.find("name")
    if name is None:
        print("Section with no name")
        return ""
    return "\n" + "#" * level + " " + name.text + " " + anchor + "\n"


def extract_xref(elem):
    target = elem.get("target")
    section = elem.get("section")
    section_format = elem.get("sectionFormat")

    if target is None:
        print("Missing target in xref")
        return "badxref"
    if target.startswith("RFC"):
        if section_format != "of" and section_format != "comma":
            print("Unsupported xref section format: " + section_format)
            return "badxref"
        if section is None:
            return "{{" + target + "}}"
        else:
            if section_format == "of":
                return "Section " + section + " of {{" + target + "}}"
            else:  # comma
                return "{{" + target + "}}, Section " + section
    return "{{" + target + "}}"


def extract_sections(root, level, bulleted):
    """Extract text from a sequence of <t> elements, possibly nested
"""
    output = ""
    if root.text is not None:
        output += collapse_spaces(root.text)
    for elem in root:
        match elem.tag:
            case "t":
                output += extract_sections(elem, level, False)
                output += "\n"
            case "li":
                pre = "* " if bulleted else ""
                output += pre + extract_sections(elem, level, False)
                output += "\n"
            case "section":
                output += section_title(elem, level + 1)
                output += extract_sections(elem, level + 1, False)
                output += "\n"
            case "ul":
                output += extract_sections(elem, level, True)
            case "xref":
                output += extract_xref(elem)
            case "bcp14":
                output += elem.text
            case "name":
                pass  # section name is processed by section_title()
            case _:
                print("Skipping unknown element: ", elem.tag)
        if elem.tail is not None:
            output += collapse_spaces(elem.tail)
    return output


def extract_preamble(root):
    output = ""
    front = root.find("front")
    if front == "":
        sys.exit("No abstract found")

    title_el = front.find("title")
    title = title_el.text
    abbrev = title_el.get("abbrev")
    rfc = root
    docname = rfc.get("docName")
    category = rfc.get("category")

    preamble = {"title": title, "abbrev": abbrev, "docname": docname, "category": category, }
    output += yaml.dump(preamble)
    return output


def parse_rfc(infile):
    output = ""
    tree = ET.parse(infile)
    root = tree.getroot()
    if root.tag != "rfc":
        sys.exit("Tag not found:\"rfc\"")

    t = extract_preamble(root)
    output += "---\n"
    output += t
    output += "\n"

    abstract = root.find("front/abstract")
    if abstract == "":
        sys.exit("No abstract found")
    t = extract_text(abstract)
    output += "--- abstract\n\n"
    output += t
    output += "\n\n"

    middle = root.find("middle")
    if middle == "":
        sys.exit("Cannot find middle part of document")
    t = extract_sections(middle, 0, False)
    output += "--- middle\n\n"
    output += t

    back = root.find("back")
    if back != "":
        t = extract_sections(back, 0, False)
        output += "--- back\n\n"
        output += t

    return output


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: " + sys.argv[0] + " infile outfile")
    infile = sys.argv[1]
    outfile = sys.argv[2]

    markdown = parse_rfc(infile)
    out = open(outfile, "w")
    out.write(markdown)


if __name__ == "__main__":
    main()
