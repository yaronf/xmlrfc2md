import xml.etree.ElementTree as ET
import yaml  # pyyaml package
import sys


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
    return "#"*level + " " + name.text + " " + anchor + "\n"


def extract_sections(root, level):
    """Extract text from a sequence of <t> elements, possibly nested
"""
    output = ""
    if root.text is not None:
        output += root.text.lstrip()
    for elem in root:
        match elem.tag:
            case "t":
                output += extract_sections(elem, level)
                output += "\n\n"
            case "section":
                output += section_title(elem, level + 1)
                output += extract_sections(elem, level + 1)
                output += "\n\n"
            case "bcp14":
                output += elem.text
            case "name":
                pass  # section name is processed by section_title()
            case _:
                print("Skipping unknown element: ", elem.tag)
        if elem.tail is not None:
            output += elem.tail
    return output


def parse_rfc(infile):
    output = ""
    tree = ET.parse(infile)
    root = tree.getroot()
    if root.tag != "rfc":
        sys.exit("Tag not found:\"rfc\"")

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
    t = extract_sections(middle, 0)
    output += "--- middle\n\n"
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
