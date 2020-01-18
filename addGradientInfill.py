#!/usr/bin/env python3
"""
Gradient Infill for 3D prints.

License: MIT
Author: Stefan Hermann - CNC Kitchen
Version: 1.0
"""
import re
from collections import namedtuple
from enum import Enum
from typing import List, Tuple

__version__ = '1.0.1.1'

class InfillType(Enum):
    """Enum for infill type."""
    NOTHING = 0
    SMALL_SEGMENTS = 1  # infill with small segments like honeycomb or gyroid
    LINEAR = 2  # linear infill like rectilinear or triangles


class Section(Enum):
    """Enum for section type."""

    NOTHING = 0
    INNER_WALL = 1
    INFILL = 2


class Slicer(Enum):
    """Enum for Slicer type."""

    NOTHING = 0
    SIMPLIFY = 1
    CURA = 2

Point2D = namedtuple('Point2D', 'x y')
Segment = namedtuple('Segment', 'point1 point2')


"""
Simplify

; layer 12, Z = 3.680
; feature inner perimeter
; feature outer perimeter
; feature infill
; layer 13, Z = 4.000


Cura
;MESH:NONMESH
G0 F300 X218.928 Y121.176 Z3.52
G0 F9000 X224.033 Y141.677
G0 X228.248 Y154.581
G0 X289.844 Y315.1
;TIME_ELAPSED:9657.948732
;LAYER:10
;TYPE:WALL-INNER
;MESH:Pico VG-single.stl
;TYPE:WALL-OUTER
;TYPE:FILL
;MESH:NONMESH
G0 F300 X284.42 Y266.642 Z3.84
"""


def dist(segment: Segment, point: Point2D) -> float:
    """Calculate the distance from a point to a line with finite length.

    Args:
        segment (Segment): line used for distance calculation
        point (Point2D): point used for distance calculation

    Returns:
        float: distance between ``segment`` and ``point``
    """
    px = segment.point2.x - segment.point1.x
    py = segment.point2.y - segment.point1.y
    norm = px * px + py * py
    u = ((point.x - segment.point1.x) * px + (point.y - segment.point1.y) * py) / float(norm)
    if u > 1:
        u = 1
    elif u < 0:
        u = 0
    x = segment.point1.x + u * px
    y = segment.point1.y + u * py
    dx = x - point.x
    dy = y - point.y

    return (dx * dx + dy * dy) ** 0.5


def get_points_distance(point1: Point2D, point2: Point2D) -> float:
    """Calculate the euclidean distance between two points.

    Args:
        point1 (Point2D): first point
        point2 (Point2D): second point

    Returns:
        float: euclidean distance between the points
    """
    return ((point1.x - point2.x) ** 2 + (point1.y - point2.y) ** 2) ** 0.5


def min_distance_from_segment(segment: Segment, segments: List[Segment]) -> float:
    """Calculate the minimum distance from the midpoint of ``segment`` to the nearest segment in ``segments``.

    Args:
        segment (Segment): segment to use for midpoint calculation
        segments (List[Segment]): segments list

    Returns:
        float: the smallest distance from the midpoint of ``segment`` to the nearest segment in the list
    """
    middlePoint = Point2D((segment.point1.x + segment.point2.x) / 2, (segment.point1.y + segment.point2.y) / 2)

    return min(dist(s, middlePoint) for s in segments)


def getXY(currentLine: str) -> Point2D:
    """Create a ``Point2D`` object from a gcode line.

    Args:
        currentLine (str): gcode line

    Raises:
        SyntaxError: when the regular expressions cannot find the relevant coordinates in the gcode

    Returns:
        Point2D: the parsed coordinates
    """
    searchX = re.search(r"X(\d*\.?\d*)", currentLine)
    searchY = re.search(r"Y(\d*\.?\d*)", currentLine)
    if searchX and searchY:
        elementX = searchX.group(1)
        elementY = searchY.group(1)
    else:
        raise SyntaxError(f'Gcode file parsing error for line {currentLine}')

    return Point2D(float(elementX), float(elementY))


def mapRange(a: Tuple[float, float], b: Tuple[float, float], s: float) -> float:
    """Calculate a multiplier for the extrusion value from the distance to the perimeter.

    Args:
        a (Tuple[float, float]): a tuple containing:
            - a1 (float): the minimum distance to the perimeter (always zero at the moment)
            - a2 (float): the maximum distance to the perimeter where the interpolation is performed
        b (Tuple[float, float]): a tuple containing:
            - b1 (float): the maximum flow as a fraction
            - b2 (float): the minimum flow as a fraction
        s (float): the euclidean distance from the middle of a segment to the nearest perimeter

    Returns:
        float: a multiplier for the modified extrusion value
    """
    (a1, a2), (b1, b2) = a, b

    return b1 + ((s - a1) * (b2 - b1) / (a2 - a1))


def get_extrusion_command(x: float, y: float, extrusion: float) -> str:
    """Format a gcode string from the X, Y coordinates and extrusion value.

    Args:
        x (float): X coordinate
        y (float): Y coordinate
        extrusion (float): Extrusion value

    Returns:
        str: Gcode line
    """
    return "G1 X{} Y{} E{}\n".format(round(x, 3), round(y, 3), round(extrusion, 5))


def is_begin_layer_line(line: str) -> bool:
    """Check if current line is the start of a layer section.

    Args:
        line (str): Gcode line

    Returns:
        bool: True if the line is the start of a layer section
    """

    if SLICER_TYPE == Slicer.SIMPLIFY:
        return line.startswith("; layer")
    elif SLICER_TYPE == Slicer.CURA:
        return line.startswith(";LAYER")


def is_begin_inner_wall_line(line: str) -> bool:
    """Check if current line is the start of an inner wall section.

    Args:
        line (str): Gcode line

    Returns:
        bool: True if the line is the start of an inner wall section
    """

    if SLICER_TYPE == Slicer.SIMPLIFY:
        return line.startswith("; feature inner perimeter")
    elif  SLICER_TYPE == Slicer.CURA:
        return line.startswith(";TYPE:WALL-INNER")


def is_end_inner_wall_line(line: str) -> bool:
    """Check if current line is the start of an outer wall section.

    Args:
        line (str): Gcode line

    Returns:
        bool: True if the line is the start of an outer wall section
    """

    if SLICER_TYPE == Slicer.SIMPLIFY:
        return line.startswith("; feature outer perimeter")
    elif  SLICER_TYPE == Slicer.CURA:
        return line.startswith(";TYPE:WALL-OUTER") or line.startswith(";TYPE:FILL")


def is_extrusion_line(line: str) -> bool:
    """Check if current line is a standard printing segment.

    Args:
        line (str): Gcode line

    Returns:
        bool: True if the line is a standard printing segment
    """
    return "G1" in line and " X" in line and "Y" in line and "E" in line


def is_begin_infill_segment_line(line: str) -> bool:
    """Check if current line is the start of an infill.

    Args:
        line (str): Gcode line

    Returns:
        bool: True if the line is the start of an infill section
    """
    if SLICER_TYPE == Slicer.SIMPLIFY:
        return line.startswith("; feature infill")
    elif  SLICER_TYPE == Slicer.CURA:
        return line.startswith(";TYPE:FILL")

def is_feature_Start(line: str) -> bool:
    """Check if current line is the start of an infill.

    Args:
        line (str): Gcode line

    Returns:
        bool: True if the line is the start of an infill section
    """
    if SLICER_TYPE == Slicer.SIMPLIFY:
        return line.startswith("; feature")
    elif  SLICER_TYPE == Slicer.CURA:
        return line.startswith(";TYPE")
    
def isSimplify(line: str) -> bool:
    """Check if current line is created by Simplify3D(R)
 
    Args:
        line (str): Gcode line

    Returns:
        bool: True if the line is created by Simplify3D(R)
    """
    return line.startswith("; G-Code generated by Simplify3D(R)")

def isCura(line: str) -> bool:
    """Check if current line is created by Cura
 
    Args:
        line (str): Gcode line

    Returns:
        bool: True if the line is created by Cura
    """
    return line.startswith(";Generated with Cura")

class GCode:

    _writtenToFile = False
    _input_file_name = ""
    _output_file_name = ""
    _infill_type = ""
    _max_flow = 0.0
    _min_flow = 0.0
    _gradient_thickness = 0.0
    _gradient_discretization = 0.0
    _infill_type = InfillType.NOTHING
    _gcodeFile = None 

    def __init__(self,
        input_file_name: str,
        output_file_name: str,
        infill_type: InfillType,
        max_flow: float,
        min_flow: float,
        gradient_thickness: float,
        gradient_discretization: float):
            _input_file_name = input_file_name
            _output_file_name = output_file_name
            _infill_type = infill_type
            _max_flow = max_flow
            _min_flow = min_flow
            _gradient_thickness = gradient_thickness
            _gradient_discretization = gradient_discretization
            
    
    def process_Non_Linear(self):
        # gyroid or honeycomb
        if _infill_type == InfillType.SMALL_SEGMENTS:
            shortestDistance = min_distance_from_segment(
                Segment(lastPosition, currentPosition), perimeterSegments
            )

            outPutLine = ""
            if shortestDistance < _gradient_thickness:
                for element in splitLine:
                    if "E" in element:
                        newE = float(element[1:]) * mapRange(
                            (0, _gradient_thickness), (_max_flow / 100, _min_flow / 100), shortestDistance
                        )
                        outPutLine = outPutLine + "E" + str(round(newE, 5))
                    else:
                        outPutLine = outPutLine + element + " "
                outPutLine = outPutLine + "\n"
                outputFile.write(outPutLine)
                _writtenToFile = True

    def process_Linear(self):
        if is_extrusion_line(currentLine):
            currentPosition = getXY(currentLine)
            splitLine = currentLine.split(" ")

            if _infill_type == InfillType.LINEAR:
                # find extrusion length
                for element in splitLine:
                    if "E" in element:
                        extrusionLength = float(element[1:])
                        
                segmentLength = get_points_distance(lastPosition, currentPosition)
                segmentSteps = segmentLength / gradientDiscretizationLength
                extrusionLengthPerSegment = extrusionLength / segmentSteps
                
                segmentDirection = Point2D(
                    (currentPosition.x - lastPosition.x) / segmentLength * gradientDiscretizationLength,
                    (currentPosition.y - lastPosition.y) / segmentLength * gradientDiscretizationLength,
                )
                
                if segmentSteps >= 2:
                    for step in range(int(segmentSteps)):
                        segmentEnd = Point2D(
                            lastPosition.x + segmentDirection.x, lastPosition.y + segmentDirection.y
                        )
                        shortestDistance = min_distance_from_segment(
                            Segment(lastPosition, segmentEnd), perimeterSegments
                        )
                        if shortestDistance < _gradient_thickness:
                            segmentExtrusion = extrusionLengthPerSegment * mapRange(
                                (0, _gradient_thickness), (_max_flow / 100, _min_flow / 100), shortestDistance
                            )
                        else:
                            segmentExtrusion = extrusionLengthPerSegment * _min_flow / 100

                        outputFile.write(get_extrusion_command(segmentEnd.x, segmentEnd.y, segmentExtrusion))
                        _writtenToFile = True

                        lastPosition = segmentEnd
                    # MissingSegment
                    segmentLengthRatio = get_points_distance(lastPosition, currentPosition) / segmentLength

                    outputFile.write(
                        get_extrusion_command(
                            currentPosition.x,
                            currentPosition.y,
                            segmentLengthRatio * extrusionLength * _max_flow / 100,
                        )
                    )
                    _writtenToFile = True
                else:
                    outPutLine = ""
                    for element in splitLine:
                        if "E" in element:
                            outPutLine = outPutLine + "E" + str(round(extrusionLength * _max_flow / 100, 5))
                        else:
                            outPutLine = outPutLine + element + " "
                    outPutLine = outPutLine + "\n"
                    outputFile.write(outPutLine)
                    
                    _writtenToFile = True

    def run(self) -> None:

        with open(input_file_name, "r") as gcodeFile, open(_output_file_name, "w+") as outputFile:
            _gcodeFile = gcodeFile
            SLICER_TYPE = Slicer.NOTHING
            
            for currentLine in gcodeFile.readline():
                determineSlicer(currentLine)
                
                if SLICER_TYPE != Slicer.NOTHING:
                    break
                
            if SLICER_TYPE == Slicer.NOTHING:
                # write message
                return

            process_gcode()

    def determineSlicer(self, currentLine: str) -> None:
        #; G-Code generated by Simplify3D(R)
        # ;Generated with Cura

        if "G-Code generated by Simplify3D" in currentLine:
            SLICER_TYPE = Slicer.SIMPLIFY
        elif "Generated with Cura" in currentLine:
            SLICER_TYPE = Slicer.CURA

    def process_gcode(self ) -> None:

    
        """Parse input Gcode file and modify infill portions with an extrusion width gradient."""
        currentSection = Section.NOTHING
        lastPosition = Point2D(-10000, -10000)
        gradientDiscretizationLength = _gradient_thickness / _gradient_discretization

        foundFirstLine = False
      
        for currentLine in _gcodeFile:
                
            writtenToFile = False
                             
            if is_begin_layer_line(currentLine):
                perimeterSegments = []
                continue
            
            if is_begin_inner_wall_line(currentLine):
                currentSection = Section.INNER_WALL
                continue

            if currentSection == Section.INNER_WALL and is_extrusion_line(currentLine):
                perimeterSegments.append(Segment(getXY(currentLine), lastPosition))
                continue

            if is_begin_infill_segment_line(currentLine):
                currentSection = Section.INFILL
                outputFile.write(currentLine)
                continue

            if is_end_inner_wall_line(currentLine):
                currentSection = Section.NOTHING
                outputFile.write(currentLine)
                continue
            
            if ";" in currentLine :
                outputFile.write(currentLine)
                continue
            
            if currentSection == Section.INFILL:
                if "F" in currentLine and "G1" in currentLine:
                    # python3.6+ f-string variant:
                    # outputFile.write("G1 F{ re.search(r"F(\d*\.?\d*)", currentLine).group(1)) }\n"
                    searchSpeed = re.search(r"F(\d*\.?\d*)", currentLine)
                    
                    if searchSpeed:
                        outputFile.write("G1 F{}\n".format(searchSpeed.group(1)))
                    else:
                        raise SyntaxError(f'Gcode file parsing error for line {currentLine}')
                    
                    process_Linear()

                    if not _writtenToFile:   
                        process_Non_Linear()

                # line with move
                if " X" in currentLine and " Y" in currentLine and ("G1" in currentLine or "G0" in currentLine):
                    lastPosition = getXY(currentLine)

                # write uneditedLine
                if not writtenToFile:
                    outputFile.write(currentLine)

#end of GCode
                

                
# EDIT this section for your creation parameters

INPUT_FILE_NAME = "cloverleaf_wHole_gyroid.gcode"
OUTPUT_FILE_NAME = "BOWDEN_cloverleaf_wHole_gyroid.gcode"

INFILL_TYPE = InfillType.SMALL_SEGMENTS
SLICER_TYPE = Slicer.NOTHING

MAX_FLOW = 350.0  # maximum extrusion flow
MIN_FLOW = 50.0  # minimum extrusion flow
GRADIENT_THICKNESS = 6.0  # thickness of the gradient (max to min) in mm
GRADIENT_DISCRETIZATION = 4.0  # only applicable for linear infills; number of segments within the
# gradient(segmentLength=gradientThickness / gradientDiscretization); use sensible values to not overload the printer

# End edit

if __name__ == '__main__':
    program = GCode(
        INPUT_FILE_NAME, OUTPUT_FILE_NAME, INFILL_TYPE, MAX_FLOW, MIN_FLOW, GRADIENT_THICKNESS, GRADIENT_DISCRETIZATION
    )

    program.run()

