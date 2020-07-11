#
# Copyright (c) 2020 FRC Team 3260
#

import numpy as np
import geometry as geom


class Planning:
    def __init__(self, config):
        self.field = config.outer_wall
        self.field_elements = config.field_elements
        self.red_goal_region = config.red_goal_region
        self.blue_goal_region = config.blue_goal_region
        self.static_obstacles = config.field_elements

        self.prev_obstacles = None
        self.occupancy_grid_dilation_kernel_size = config.occupancy_grid_dilation_kernel_size
        self.occupancy_grid = geom.OccupancyGrid(config.occupancy_grid_width,
                                                 config.occupancy_grid_height,
                                                 config.occupancy_grid_cell_resolution,
                                                 config.occupancy_grid_origin)

    def run(self, world_state):
        # 1. Identify the goal
        self.behavior_planning(world_state)

        # 2. Move towards it if there is a nearest ball (using A*)
        self.motion_planning(world_state)

        plan_state = {
            'pose': world_state['pose'],
            'trajectory': world_state['trajectory'],
            'grid': world_state['grid'],
            'goal': world_state['goal'],
            'direction': world_state['direction'],
            'tube_mode': world_state['tube_mode']
        }
        return plan_state

    def behavior_planning(self, world_state):
        """
        Identifies a goal state and places it into world_state['goal'].

        Also identify what action we want to take, as world_state['tube_mode'] which
        is one of 'INTAKE', 'OUTTAKE', 'NONE'. Also identify which direction to drive in,
        one of '1', '-1', or '0'
        """
        start = world_state['pose'][0]  # Our current (x,y)
        scoring_zone = (self.blue_goal_region.center[0], self.blue_goal_region.center[1] + 1)

        '''
        ### lazy f-strings for programmers and debug output (new in python3 (3.8?)):
        In [3]: x = {1:2, 3:4}
        In [5]: y = "nice"
        In [6]: print(f"{x[1]=}, {y=}")
        x[1]=2, y='nice'
        '''
        if world_state['ingestedBalls'] > 4 or (geom.dist(start, scoring_zone) <= 0.15 and world_state['ingestedBalls'] > 0):

            # If we're close to pregoal then run the tube
            if geom.dist(start, scoring_zone) <= 0.15:
                tube_mode = 'OUTTAKE'
                direction = 0
                goal = scoring_zone
            # Else go towards pregoal
            else:
                tube_mode = 'INTAKE'
                direction = -1
                goal = scoring_zone
        else:
            tube_mode = 'INTAKE'
            direction = 1
            # 1. Add some object persistence so balls inside the LIDAR deadzone don't keep going out of view
            deadzone_radius = 0.85
            if self.prev_obstacles is not None:
                # Run through and recover any balls within the deadzone and place them into world_state
                for ball in self.prev_obstacles:
                    if 0.5 < geom.dist(start, ball[0]) < deadzone_radius:
                        world_state['obstacles']['balls'].append(ball)
            self.prev_obstacles = world_state['obstacles']['balls']

            # 2. Find the closest ball
            min_dist = np.inf
            goal = None
            for ball in world_state['obstacles']['balls']:
                curr_dist = geom.dist(ball[0], start)
                if curr_dist < min_dist and not self.occupancy_grid.occupancy[self.occupancy_grid.get_cell(ball[0]).indices]:
                    min_dist = curr_dist
                    goal = ball[0]

        world_state['goal'] = goal
        world_state['direction'] = direction
        world_state['tube_mode'] = tube_mode

    def motion_planning(self, world_state):
        """
        Identifies a motion plan for achieving the goal state contained in world_state['goal'] and places a
        trajectory waypoint into world_state['waypoint'].
        """
        # clear the positions previously marked as obstacles because they may have changed
        self.occupancy_grid.clear()

        # Insert static obstacles
        for static_obstacle in self.static_obstacles:
            self.occupancy_grid.insert_convex_polygon(static_obstacle)

        # Insert dynamic obstacles
        dynamic_obstacles = world_state['obstacles']['others']
        for dynamic_obstacle in dynamic_obstacles:
            self.occupancy_grid.insert_rectangular_obstacle(dynamic_obstacle)

        self.occupancy_grid.dilate(kernel_size=self.occupancy_grid_dilation_kernel_size)

        # Call A* to generate a path to goal
        trajectory = None
        if world_state['goal'] is not None:
            start = world_state['pose'][0]
            goal = world_state['goal']
            trajectory = geom.a_star(self.occupancy_grid, start, goal)

        world_state['trajectory'] = trajectory
        world_state['grid'] = self.occupancy_grid
